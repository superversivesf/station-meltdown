"""End-to-end playtest: 4 WebSocket clients play a full game (10 survival + 3 finale).

Run: cd backend && .venv/bin/python tests/test_e2e_playtest.py
Standalone script (no pytest) — exits 0 on success, 1 on failure.

Requires the backend running on localhost:8000. The script will start it
itself if the port is free (subprocess), and tear it down on exit.
"""
import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time

import websockets

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = int(os.environ.get("E2E_PORT", "8001"))
BASE_WS = f"ws://{BACKEND_HOST}:{BACKEND_PORT}/ws"
PLAYER_NAMES = ["Alice", "Bob", "Carol", "Dave"]


def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


def start_backend() -> subprocess.Popen | None:
    """Start the backend if the port is free. Returns proc or None if already up."""
    if not port_free(BACKEND_HOST, BACKEND_PORT):
        return None  # already running — we won't own it
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", BACKEND_HOST, "--port", str(BACKEND_PORT),
        ],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for port to come up
    for _ in range(50):
        if not port_free(BACKEND_HOST, BACKEND_PORT):
            return proc
        time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("backend did not start")


def stop_backend(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


class Client:
    """One WebSocket player. Holds its assigned player_id."""

    def __init__(self, name: str, room_code: str):
        self.name = name
        self.room_code = room_code
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.player_id: str | None = None
        self.last_state: dict | None = None

    async def connect(self) -> None:
        self.ws = await websockets.connect(f"{BASE_WS}/{self.room_code}")

    async def send(self, msg: dict) -> None:
        assert self.ws is not None
        await self.ws.send(json.dumps(msg))

    async def recv_state(self, timeout: float = 5.0) -> dict:
        """Read messages until we get a `state` message; return its state dict."""
        assert self.ws is not None
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=deadline - time.time())
            except asyncio.TimeoutError:
                raise AssertionError(f"{self.name}: no state message within {timeout}s")
            data = json.loads(raw)
            if data.get("type") == "state":
                self.player_id = data.get("player_id", self.player_id)
                self.last_state = data["state"]
                return self.last_state
            # action_ack or error — loop and keep waiting for a state
        raise AssertionError(f"{self.name}: timed out waiting for state")

    async def recv_any(self, timeout: float = 2.0) -> dict | None:
        assert self.ws is not None
        try:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
            return json.loads(raw)
        except asyncio.TimeoutError:
            return None

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()
            self.ws = None


async def drain_inbox(client: Client, timeout: float = 0.3) -> None:
    """Best-effort: clear any buffered messages (esp. broadcast_state echoes)."""
    while True:
        msg = await client.recv_any(timeout=timeout)
        if msg is None:
            return
        if msg.get("type") == "state":
            client.last_state = msg["state"]
            client.player_id = msg.get("player_id", client.player_id)


def assert_eq(actual, expected, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(cond, label: str) -> None:
    if not cond:
        raise AssertionError(f"{label}: assertion failed (value={cond!r})")


async def play_one_full_game(game_idx: int) -> dict:
    """Run a complete game. Returns summary dict; raises on any invariant break."""
    room_code = f"E2E{game_idx:02d}"
    clients = [Client(name, room_code) for name in PLAYER_NAMES]

    # ---- Join phase ----
    for c in clients:
        await c.connect()
    for c in clients:
        await c.send({"type": "join", "name": c.name})
    # Each join broadcasts state to all clients; collect after the last join.
    for c in clients:
        await c.recv_state()
    # Drain any extra broadcast echoes
    for c in clients:
        await drain_inbox(c, timeout=0.2)

    state = clients[0].last_state
    assert_eq(state["phase"], "lobby", f"[{room_code}] phase after join")
    assert_eq(len(state["players"]), 4, f"[{room_code}] player count")
    names = sorted(p["name"] for p in state["players"])
    assert_eq(names, sorted(PLAYER_NAMES), f"[{room_code}] player names")
    assert_true(
        any(p["is_host"] for p in state["players"]),
        f"[{room_code}] host assigned",
    )
    print(f"  [{room_code}] 4 players joined; lobby OK")

    # ---- Start ----
    host = next(c for c in clients if c.last_state and any(
        p["is_host"] and p["id"] == c.player_id for p in c.last_state["players"]
    ))
    # Fallback: first joiner is host
    if host is None:
        host = clients[0]
    await host.send({"type": "start"})
    for c in clients:
        await c.recv_state()
    for c in clients:
        await drain_inbox(c, timeout=0.2)

    state = clients[0].last_state
    assert_eq(state["phase"], "survival", f"[{room_code}] phase after start")
    assert_eq(state["round_number"], 1, f"[{room_code}] round after start")
    expected_crises = 1  # round 1
    assert_eq(
        len(state["active_crises"]), expected_crises,
        f"[{room_code}] crises round 1",
    )
    # All systems start at 100
    for sys_name, hp in state["systems"].items():
        assert_eq(hp, 100, f"[{room_code}] {sys_name} starts at 100")
    print(f"  [{room_code}] game started; survival round 1 ({expected_crises} crisis)")

    # ---- Survival rounds 1-10 ----
    expected_crises_by_round = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2, 7: 2, 8: 3, 9: 3, 10: 3}
    for rnd in range(1, 11):
        state = clients[0].last_state
        assert_eq(state["phase"], "survival", f"[{room_code}] phase round {rnd}")
        assert_eq(state["round_number"], rnd, f"[{room_code}] round number")
        assert_eq(
            len(state["active_crises"]), expected_crises_by_round[rnd],
            f"[{room_code}] crisis count round {rnd}",
        )
        # Crises on distinct systems
        crisis_systems = [c["system"] for c in state["active_crises"]]
        assert_true(
            len(set(crisis_systems)) == len(crisis_systems),
            f"[{room_code}] crises on distinct systems round {rnd}",
        )
        # At least one crisis has crew_required >= 2 when count >= 2 (multi-crew guarantee)
        if len(state["active_crises"]) >= 2:
            crews = [c["crew_required"] for c in state["active_crises"]]
            assert_true(
                max(crews) >= 2,
                f"[{room_code}] multi-crew guarantee round {rnd}",
            )

        # Strategy: each player FIXes a crisis if they can contribute,
        # otherwise BOLSTERs the lowest-health system.
        crises = state["active_crises"]
        # Assign players to crises greedily by crew_required
        assignments: list[dict] = []
        standing = [p for p in state["players"] if not p["is_down"]]
        pi = 0
        for crisis in crises:
            needed = crisis["crew_required"]
            for _ in range(needed):
                if pi < len(standing):
                    assignments.append({
                        "player_id": standing[pi]["id"],
                        "action": "fix",
                        "crisis_id": crisis["id"],
                        "system": crisis["system"],
                    })
                    pi += 1
        # Remaining players bolster the lowest-health system
        lowest = min(state["systems"], key=lambda s: state["systems"][s])
        for p in standing[pi:]:
            assignments.append({
                "player_id": p["id"],
                "action": "bolster",
                "system": lowest,
            })

        # Submit actions
        for c in clients:
            for a in assignments:
                if a["player_id"] == c.player_id:
                    await c.send({
                        "type": "action",
                        "action_type": a["action"],
                        "target_system": a.get("system"),
                        "target_crisis_id": a.get("crisis_id"),
                        "target_player_id": a.get("target_player_id"),
                    })
                    # Expect an action_ack
                    ack = await c.recv_any(timeout=2.0)
                    assert_true(
                        ack is not None and ack.get("type") == "action_ack",
                        f"[{room_code}] action_ack for {c.name} round {rnd}",
                    )

        # Host resolves
        await host.send({"type": "resolve"})
        for c in clients:
            await c.recv_state()
        for c in clients:
            await drain_inbox(c, timeout=0.2)

        # After resolve, verify systems didn't go negative and no reactor=0 (we play optimally)
        state = clients[0].last_state
        for sys_name, hp in state["systems"].items():
            assert_true(hp >= 0, f"[{room_code}] {sys_name} >= 0 after round {rnd}")
        # If game ended early (reactor or all-down), we still want a clean finish
        if state["phase"] == "results":
            print(f"  [{room_code}] game ended at survival round {rnd} "
                  f"(victory={state['victory']})")
            return {
                "room_code": room_code,
                "ended_early": True,
                "survival_round": rnd,
                "final_phase": "results",
                "victory": state["victory"],
                "systems": state["systems"],
            }
        print(f"  [{room_code}] survival round {rnd} resolved; "
              f"systems: " + ", ".join(
                  f"{k[:4]}={v}" for k, v in state["systems"].items()
              ))

    # After 10 rounds, should transition to finale
    state = clients[0].last_state
    assert_eq(state["phase"], "finale", f"[{room_code}] transition to finale")
    assert_eq(state["round_number"], 1, f"[{room_code}] finale round 1")
    assert_eq(state["collapse_bar"], 0, f"[{room_code}] collapse starts at 0")
    assert_eq(len(state["active_crises"]), 0, f"[{room_code}] no crises in finale")
    print(f"  [{room_code}] reached finale; collapse=0")

    # ---- Finale rounds 1-3 ----
    # Strategy: standing players RUN, downed players get CARRIED (needs 2).
    for fr in range(1, 4):
        state = clients[0].last_state
        if state["phase"] != "finale":
            # Game already ended
            break
        assert_eq(state["round_number"], fr, f"[{room_code}] finale round num")

        standing = [p for p in state["players"] if not p["is_down"]]
        downed = [p for p in state["players"] if p["is_down"]]

        # Standing players RUN
        for p in standing:
            c = next(c for c in clients if c.player_id == p["id"])
            await c.send({"type": "action", "action_type": "run"})
            ack = await c.recv_any(timeout=2.0)
            assert_true(ack is not None and ack.get("type") == "action_ack",
                        f"[{room_code}] ack RUN {p['name']} finale r{fr}")

        # Downed players get CARRIED — assign 2 carriers each if we have enough standing
        for dp in downed:
            carriers = standing[:2]
            if len(carriers) >= 2:
                for cp in carriers:
                    c = next(c for c in clients if c.player_id == cp["id"])
                    await c.send({
                        "type": "action",
                        "action_type": "carry",
                        "target_player_id": dp["id"],
                    })
                    ack = await c.recv_any(timeout=2.0)
                    assert_true(
                        ack is not None and ack.get("type") == "action_ack",
                        f"[{room_code}] ack CARRY finale r{fr}",
                    )

        await host.send({"type": "resolve"})
        for c in clients:
            await c.recv_state()
        for c in clients:
            await drain_inbox(c, timeout=0.2)

        state = clients[0].last_state
        # Collapse bar should increase (base +34, minus holds if any). No holds here.
        # Each round with no holds → +34. We didn't HOLD, so it grows.
        if state["phase"] == "finale":
            assert_true(
                state["collapse_bar"] > 0 or fr == 1 and state["collapse_bar"] == 0,
                f"[{room_code}] collapse grows finale r{fr} (got {state['collapse_bar']})",
            )
        # escape_track for standing should advance (capped at 3)
        for p in state["players"]:
            if not p["is_down"]:
                assert_true(
                    p["escape_track"] <= 3,
                    f"[{room_code}] escape cap for {p['name']}",
                )
        print(f"  [{room_code}] finale round {fr} resolved; "
              f"collapse={state['collapse_bar']}, "
              f"escapes=" + ",".join(
                  f"{p['name'][:3]}={p['escape_track']}" for p in state["players"]
              ))

        if state["phase"] == "results":
            print(f"  [{room_code}] finale ended at round {fr} "
                  f"(victory={state['victory']}, partial={state.get('partial')})")
            break

    state = clients[0].last_state
    assert_eq(state["phase"], "results", f"[{room_code}] final phase is results")
    # survivor/lost lists should be present and partition the players
    survived = set(state.get("crew_survived", []))
    lost = set(state.get("crew_lost", []))
    all_ids = {p["id"] for p in state["players"]}
    assert_true(
        survived | lost == all_ids and not (survived & lost),
        f"[{room_code}] survivor/lost partition is valid",
    )
    print(f"  [{room_code}] results: victory={state['victory']}, "
          f"partial={state.get('partial')}, "
          f"survived={len(survived)}, lost={len(lost)}")

    return {
        "room_code": room_code,
        "ended_early": False,
        "final_phase": state["phase"],
        "victory": state["victory"],
        "partial": state.get("partial", False),
        "survived": len(survived),
        "lost": len(lost),
        "systems": state["systems"],
    }


async def main() -> int:
    print("=== Station Meltdown E2E Playtest ===")
    proc = start_backend()
    print(f"backend on :{BACKEND_PORT} (owned={'yes' if proc else 'no'})")

    results: list[dict] = []
    failures: list[str] = []
    n_games = 3
    for i in range(1, n_games + 1):
        print(f"\n--- Game {i}/{n_games} ---")
        try:
            summary = await play_one_full_game(i)
            results.append(summary)
            print(f"  -> OK: {summary}")
        except AssertionError as e:
            failures.append(f"Game {i}: {e}")
            print(f"  -> FAIL: {e}")
        except Exception as e:
            failures.append(f"Game {i} (exception): {e!r}")
            print(f"  -> ERROR: {e!r}")
        finally:
            # Clean up clients for this game
            pass

    stop_backend(proc)

    print("\n=== Summary ===")
    for r in results:
        print(f"  {r['room_code']}: victory={r.get('victory')} "
              f"partial={r.get('partial')} survived={r.get('survived')} "
              f"lost={r.get('lost')}")
    if failures:
        print(f"\nFAILED ({len(failures)} game(s)):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\nALL {len(results)} GAMES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))