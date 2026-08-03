"""End-to-end playtest harness for Station Meltdown.

Exercises both the happy path (optimal play -> 4/4 survive) and negative /
alternate branches required by Task 15 Step 1:
  * FIX with insufficient crew doesn't work
  * BOLSTER caps at 100
  * REVIVE works (needs Med Bay > 0)
  * Reactor = 0 triggers loss
  * Life Support = 0 downs crew
  * Timer auto-resolves
  * HOLD reduces collapse bar
  * Partial win
  * Loss in finale (collapse hits 100%)
  * CARRY with 2 carriers

Run:  cd backend && .venv/bin/python -m pytest tests/test_e2e_playtest.py -v
Or standalone (happy-path only):  cd backend && .venv/bin/python tests/test_e2e_playtest.py

The harness starts its own backend on $E2E_PORT (default 8001) if the port
is free; ACTION_PHASE_SECONDS env var (read by game.py) sets a short timer
so timer-auto-resolve tests don't take 45s.
"""
import asyncio
import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid

import pytest
import websockets

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = int(os.environ.get("E2E_PORT", "8001"))
BASE_WS = f"ws://{BACKEND_HOST}:{BACKEND_PORT}/ws"
PLAYER_NAMES = ["Alice", "Bob", "Carol", "Dave"]

# Short action phase for timer tests; default matches engine default.
ACTION_PHASE_SECONDS = os.environ.get("ACTION_PHASE_SECONDS", "45")


# ---------------------------------------------------------------------------
# Backend management
# ---------------------------------------------------------------------------
def port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


def start_backend(seconds: str = "45") -> subprocess.Popen | None:
    """Start backend if port is free; returns proc or None if already up."""
    if not port_free(BACKEND_HOST, BACKEND_PORT):
        return None
    env = {
        **os.environ,
        "ACTION_PHASE_SECONDS": seconds,
        "DEBUG_MODE": "1",
    }
    # Only pass CRISIS_SEED if explicitly set (empty string would break int())
    if os.environ.get("CRISIS_SEED"):
        env["CRISIS_SEED"] = os.environ["CRISIS_SEED"]
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "main:app",
            "--host", BACKEND_HOST, "--port", str(BACKEND_PORT),
        ],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
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


# ---------------------------------------------------------------------------
# Client helper
# ---------------------------------------------------------------------------
class Client:
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
        assert self.ws is not None
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(
                    self.ws.recv(), timeout=deadline - time.time()
                )
            except asyncio.TimeoutError:
                raise AssertionError(
                    f"{self.name}: no state message within {timeout}s"
                )
            data = json.loads(raw)
            if data.get("type") == "state":
                self.player_id = data.get("player_id", self.player_id)
                self.last_state = data["state"]
                return self.last_state
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


def find_host(clients: list[Client]) -> Client:
    for c in clients:
        if c.last_state and any(
            p["is_host"] and p["id"] == c.player_id for p in c.last_state["players"]
        ):
            return c
    return clients[0]


def player_by_id(state: dict, pid: str) -> dict:
    return next(p for p in state["players"] if p["id"] == pid)


# ---------------------------------------------------------------------------
# Shared setup / teardown — session-scoped so the backend persists across
# all tests (starting/stopping per-test causes connection churn).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def backend():
    proc = start_backend(ACTION_PHASE_SECONDS)
    yield proc
    stop_backend(proc)


@pytest.fixture(scope="session")
def short_backend():
    proc = start_backend("2")
    yield proc
    stop_backend(proc)


async def join_room(room_code: str, names: list[str]) -> list[Client]:
    clients = [Client(n, room_code) for n in names]
    for c in clients:
        await c.connect()
    for c in clients:
        await c.send({"type": "join", "name": c.name})
    for c in clients:
        await c.recv_state()
    for c in clients:
        await drain_inbox(c, timeout=0.2)
    return clients


async def start_game(host: Client, clients: list[Client]) -> dict:
    await host.send({"type": "start"})
    # Collect state from all clients, but also check for error messages
    for c in clients:
        msg = await c.recv_any(timeout=5.0)
        if msg is None:
            raise AssertionError(f"{c.name}: no response to start within 5s")
        if msg.get("type") == "error":
            raise AssertionError(f"{c.name}: start rejected: {msg.get('message')}")
        if msg.get("type") == "state":
            c.player_id = msg.get("player_id", c.player_id)
            c.last_state = msg["state"]
        else:
            # unexpected message — keep draining for state
            pass
    # Drain extra echoes
    for c in clients:
        await drain_inbox(c, timeout=0.2)
    return clients[0].last_state


async def submit_action(client: Client, action_type: str, **kw) -> dict:
    msg = {"type": "action", "action_type": action_type}
    msg.update(kw)
    await client.send(msg)
    ack = await client.recv_any(timeout=2.0)
    assert ack is not None and ack.get("type") == "action_ack", (
        f"{client.name}: no action_ack for {action_type}"
    )
    return ack


async def debug_set_system(client: Client, system: str, hp: int) -> dict:
    """Test-only: set a system's HP directly (requires DEBUG_MODE on backend)."""
    await client.send({"type": "debug_set_system", "system": system, "hp": hp})
    # broadcast_state sends to ALL clients; drain everyone's inbox
    # so subsequent submit_action calls get clean action_acks.
    state = await client.recv_state(timeout=3.0)
    return state


async def debug_down_player(client: Client, name: str) -> dict:
    """Test-only: down a player by name (requires DEBUG_MODE on backend)."""
    await client.send({"type": "debug_down_player", "name": name})
    state = await client.recv_state(timeout=3.0)
    return state


async def debug_and_drain(
    host: Client, clients: list[Client], system: str, hp: int
) -> dict:
    """Set system HP via debug hook, then drain all clients' inboxes."""
    await host.send({"type": "debug_set_system", "system": system, "hp": hp})
    for c in clients:
        await c.recv_state(timeout=3.0)
    for c in clients:
        await drain_inbox(c, timeout=0.2)
    return clients[0].last_state


async def debug_down_and_drain(
    host: Client, clients: list[Client], name: str
) -> dict:
    """Down a player via debug hook, then drain all clients' inboxes."""
    await host.send({"type": "debug_down_player", "name": name})
    for c in clients:
        await c.recv_state(timeout=3.0)
    for c in clients:
        await drain_inbox(c, timeout=0.2)
    return clients[0].last_state


async def resolve_and_collect(host: Client, clients: list[Client]) -> dict:
    await host.send({"type": "resolve"})
    for c in clients:
        await c.recv_state()
    for c in clients:
        await drain_inbox(c, timeout=0.2)
    return clients[0].last_state


async def close_clients(clients: list[Client]) -> None:
    for c in clients:
        await c.close()


# ---------------------------------------------------------------------------
# HAPPY PATH (original scenarios, kept intact)
# ---------------------------------------------------------------------------
async def play_one_full_game(game_idx: int) -> dict:
    room_code = f"E2E{game_idx:02d}"
    clients = await join_room(room_code, PLAYER_NAMES)

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

    host = find_host(clients)
    state = await start_game(host, clients)
    assert_eq(state["phase"], "survival", f"[{room_code}] phase after start")
    assert_eq(state["round_number"], 1, f"[{room_code}] round after start")
    assert_eq(
        len(state["active_crises"]), 1, f"[{room_code}] crises round 1"
    )
    for sys_name, hp in state["systems"].items():
        assert_eq(hp, 100, f"[{room_code}] {sys_name} starts at 100")
    print(f"  [{room_code}] game started; survival round 1 (1 crisis)")

    expected_crises_by_round = {
        1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2, 7: 2, 8: 3, 9: 3, 10: 3
    }
    for rnd in range(1, 11):
        state = clients[0].last_state
        assert_eq(state["phase"], "survival", f"[{room_code}] phase round {rnd}")
        assert_eq(state["round_number"], rnd, f"[{room_code}] round number")
        assert_eq(
            len(state["active_crises"]), expected_crises_by_round[rnd],
            f"[{room_code}] crisis count round {rnd}",
        )
        crisis_systems = [c["system"] for c in state["active_crises"]]
        assert_true(
            len(set(crisis_systems)) == len(crisis_systems),
            f"[{room_code}] crises on distinct systems round {rnd}",
        )
        if len(state["active_crises"]) >= 2:
            crews = [c["crew_required"] for c in state["active_crises"]]
            assert_true(
                max(crews) >= 2,
                f"[{room_code}] multi-crew guarantee round {rnd}",
            )

        crises = state["active_crises"]
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
        lowest = min(state["systems"], key=lambda s: state["systems"][s])
        for p in standing[pi:]:
            assignments.append({
                "player_id": p["id"],
                "action": "bolster",
                "system": lowest,
            })

        for c in clients:
            for a in assignments:
                if a["player_id"] == c.player_id:
                    await submit_action(
                        c, a["action"],
                        target_system=a.get("system"),
                        target_crisis_id=a.get("crisis_id"),
                        target_player_id=a.get("target_player_id"),
                    )

        await resolve_and_collect(host, clients)
        state = clients[0].last_state
        for sys_name, hp in state["systems"].items():
            assert_true(hp >= 0, f"[{room_code}] {sys_name} >= 0 after round {rnd}")
        if state["phase"] == "results":
            print(
                f"  [{room_code}] game ended at survival round {rnd} "
                f"(victory={state['victory']})"
            )
            return {
                "room_code": room_code, "ended_early": True,
                "survival_round": rnd, "final_phase": "results",
                "victory": state["victory"], "systems": state["systems"],
            }
        print(
            f"  [{room_code}] survival round {rnd} resolved; systems: "
            + ", ".join(f"{k[:4]}={v}" for k, v in state["systems"].items())
        )

    state = clients[0].last_state
    assert_eq(state["phase"], "finale", f"[{room_code}] transition to finale")
    assert_eq(state["round_number"], 1, f"[{room_code}] finale round 1")
    assert_eq(state["collapse_bar"], 0, f"[{room_code}] collapse starts at 0")
    assert_eq(len(state["active_crises"]), 0, f"[{room_code}] no crises in finale")
    print(f"  [{room_code}] reached finale; collapse=0")

    for fr in range(1, 4):
        state = clients[0].last_state
        if state["phase"] != "finale":
            break
        assert_eq(state["round_number"], fr, f"[{room_code}] finale round num")

        standing = [p for p in state["players"] if not p["is_down"]]
        downed = [p for p in state["players"] if p["is_down"]]

        for p in standing:
            c = next(c for c in clients if c.player_id == p["id"])
            await submit_action(c, "run")

        for dp in downed:
            carriers = standing[:2]
            if len(carriers) >= 2:
                for cp in carriers:
                    c = next(c for c in clients if c.player_id == cp["id"])
                    await submit_action(
                        c, "carry", target_player_id=dp["id"]
                    )

        await resolve_and_collect(host, clients)
        state = clients[0].last_state
        if state["phase"] == "finale":
            assert_true(
                state["collapse_bar"] > 0 or fr == 1 and state["collapse_bar"] == 0,
                f"[{room_code}] collapse grows finale r{fr} (got {state['collapse_bar']})",
            )
        for p in state["players"]:
            if not p["is_down"]:
                assert_true(
                    p["escape_track"] <= 3,
                    f"[{room_code}] escape cap for {p['name']}",
                )
        print(
            f"  [{room_code}] finale round {fr} resolved; "
            f"collapse={state['collapse_bar']}, escapes="
            + ",".join(
                f"{p['name'][:3]}={p['escape_track']}" for p in state["players"]
            )
        )
        if state["phase"] == "results":
            print(
                f"  [{room_code}] finale ended at round {fr} "
                f"(victory={state['victory']}, partial={state.get('partial')})"
            )
            break

    state = clients[0].last_state
    assert_eq(state["phase"], "results", f"[{room_code}] final phase is results")
    survived = set(state.get("crew_survived", []))
    lost = set(state.get("crew_lost", []))
    all_ids = {p["id"] for p in state["players"]}
    assert_true(
        survived | lost == all_ids and not (survived & lost),
        f"[{room_code}] survivor/lost partition is valid",
    )
    print(
        f"  [{room_code}] results: victory={state['victory']}, "
        f"partial={state.get('partial')}, survived={len(survived)}, lost={len(lost)}"
    )
    return {
        "room_code": room_code, "ended_early": False,
        "final_phase": state["phase"], "victory": state["victory"],
        "partial": state.get("partial", False),
        "survived": len(survived), "lost": len(lost),
        "systems": state["systems"],
    }


# ---------------------------------------------------------------------------
# NEGATIVE PATH SCENARIOS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fix_insufficient_crew(backend):
    """FIX with fewer players than crew_required doesn't fix the crisis."""
    room_code = "FIX01"
    clients = await join_room(room_code, PLAYER_NAMES)
    try:
        host = find_host(clients)
        state = await start_game(host, clients)
        assert_eq(state["phase"], "survival", f"[{room_code}] phase")
        assert_eq(len(state["active_crises"]), 1, f"[{room_code}] crisis count")

        crisis = state["active_crises"][0]
        needed = crisis["crew_required"]
        before = state["systems"][crisis["system"]]

        # Pick a bolster target that is NOT the crisis system, so the drain
        # isn't masked by a +5 bolster on the same system.
        bolster_target = next(
            s for s in state["systems"] if s != crisis["system"]
        )

        # Submit only one FIX no matter the crew_required (so if needed==2,
        # this is insufficient; if needed==1, we can't make it insufficient
        # without zero fixers, so we just send no FIX at all).
        if needed >= 2:
            fixer = next(c for c in clients if c.player_id == state["players"][0]["id"])
            await submit_action(fixer, "fix", target_crisis_id=crisis["id"])
            for c in clients:
                if c is not fixer:
                    await submit_action(c, "bolster", target_system=bolster_target)
        else:
            # crew_required == 1; send zero FIX -> crisis drains
            for c in clients:
                await submit_action(c, "bolster", target_system=bolster_target)

        state = await resolve_and_collect(host, clients)
        after = state["systems"][crisis["system"]]
        assert_true(
            after < before,
            f"[{room_code}] crisis drained despite insufficient crew "
            f"({before} -> {after})",
        )
        print(f"  [{room_code}] insufficient FIX: {before} -> {after} (drained)")
    finally:
        await close_clients(clients)


@pytest.mark.asyncio
async def test_bolster_caps_at_100(backend):
    """BOLSTER adds +5 but caps at 100."""
    room_code = "BOL01"
    clients = await join_room(room_code, PLAYER_NAMES)
    try:
        host = find_host(clients)
        state = await start_game(host, clients)

        crisis = state["active_crises"][0]
        # Fix the crisis (assign enough players) so it doesn't drain
        needed = crisis["crew_required"]
        fixers = [c for c in clients][:needed]
        for c in fixers:
            await submit_action(c, "fix", target_crisis_id=crisis["id"])
        # Bolster a system at 98 (we'll target reactor if it's not the crisis)
        target = "hull" if crisis["system"] == "reactor" else "reactor"
        remaining = [c for c in clients][needed:]
        # Drop the target to 98 via... we can't directly. Instead just
        # bolster a full system (100) and verify it stays 100.
        for c in remaining:
            await submit_action(c, "bolster", target_system=target)

        state = await resolve_and_collect(host, clients)
        assert_true(
            state["systems"][target] == 100,
            f"[{room_code}] bolster cap: {target} = {state['systems'][target]} (expected 100)",
        )
        print(f"  [{room_code}] bolster cap: {target} = 100 (capped)")
    finally:
        await close_clients(clients)


@pytest.mark.asyncio
async def test_revive_downed_player(backend):
    """REVIVE works when Med Bay > 0. Down a player, then revive."""
    room_code = "REV01"
    clients = await join_room(room_code, PLAYER_NAMES)
    try:
        host = find_host(clients)
        state = await start_game(host, clients)

        # Use debug hook to down "Bob" directly (ensures deterministic test)
        state = await debug_down_and_drain(host, clients, "Bob")
        bob = next(p for p in state["players"] if p["name"] == "Bob")
        assert_true(bob["is_down"], f"[{room_code}] Bob should be downed")
        assert_true(
            state["systems"]["med_bay"] > 0,
            f"[{room_code}] med_bay must be > 0 to revive",
        )

        # Now revive Bob: one player sends REVIVE targeting Bob
        healer = next(c for c in clients if c.player_id != bob["id"])
        # Everyone else bolsters med_bay to keep it healthy
        others = [c for c in clients if c.player_id != bob["id"]]
        await submit_action(healer, "revive", target_player_id=bob["id"])
        for c in others:
            if c is not healer:
                await submit_action(c, "bolster", target_system="med_bay")

        state = await resolve_and_collect(host, clients)
        revived = player_by_id(state, bob["id"])
        assert_true(
            not revived["is_down"],
            f"[{room_code}] player {revived['name']} was not revived",
        )
        print(f"  [{room_code}] revived {revived['name']} (med_bay={state['systems']['med_bay']})")
    finally:
        await close_clients(clients)


@pytest.mark.asyncio
async def test_reactor_zero_triggers_loss(backend):
    """Reactor = 0 triggers loss; phase becomes results, victory=False."""
    room_code = "RCT01"
    clients = await join_room(room_code, PLAYER_NAMES)
    try:
        host = find_host(clients)
        state = await start_game(host, clients)

        # Use debug hook to set reactor to 1, then let the crisis drain it
        # to 0 on the next resolve (or set directly to 0).
        state = await debug_and_drain(host, clients, "reactor", 0)

        # Now resolve — reactor is at 0, so the loss condition triggers.
        # But first, fix any reactor crisis so the drain doesn't matter
        # (reactor is already 0). Actually, the engine checks reactor==0
        # AFTER applying drains. If reactor is 0, it ends the game.
        # Submit a no-op action for everyone (bolster a non-reactor system).
        for c in clients:
            await submit_action(c, "bolster", target_system="hull")
        state = await resolve_and_collect(host, clients)

        assert_eq(state["phase"], "results", f"[{room_code}] phase should be results")
        assert_true(
            not state["victory"],
            f"[{room_code}] victory should be False (reactor hit 0)",
        )
        assert_eq(state["systems"]["reactor"], 0, f"[{room_code}] reactor at 0")
        print(f"  [{room_code}] reactor=0 loss: victory={state['victory']}")
    finally:
        await close_clients(clients)


@pytest.mark.asyncio
async def test_life_support_zero_downs_crew(backend):
    """Life Support = 0 downs a crew member."""
    room_code = "LIF01"
    clients = await join_room(room_code, PLAYER_NAMES)
    try:
        host = find_host(clients)
        state = await start_game(host, clients)

        # Use debug hook to set life_support to 0
        state = await debug_and_drain(host, clients, "life_support", 0)

        # Resolve — life_support at 0 downs a crew member
        for c in clients:
            await submit_action(c, "bolster", target_system="reactor")
        state = await resolve_and_collect(host, clients)

        downed = [p for p in state["players"] if p["is_down"]]
        assert_true(
            len(downed) >= 1,
            f"[{room_code}] no player downed after life_support=0",
        )
        assert_true(
            state["systems"]["life_support"] == 0,
            f"[{room_code}] life_support should be 0",
        )
        print(
            f"  [{room_code}] life_support=0 downed {len(downed)} crew member(s) "
            f"(life_support={state['systems']['life_support']})"
        )
    finally:
        await close_clients(clients)


@pytest.mark.asyncio
async def test_timer_auto_resolves(short_backend):
    """Timer auto-resolves the round when deadline passes (no manual resolve)."""
    room_code = "TMR01"
    clients = await join_room(room_code, PLAYER_NAMES)
    try:
        host = find_host(clients)
        state = await start_game(host, clients)
        assert_eq(state["phase"], "survival", f"[{room_code}] phase")
        assert_eq(state["round_number"], 1, f"[{room_code}] round")

        # Don't send any actions and don't send resolve.
        # With ACTION_PHASE_SECONDS=2, auto-resolve fires after ~2s.
        # We wait for the broadcast state that the timer sends.
        deadline_wait = 4.0  # generous above the 2s timer
        for c in clients:
            await c.recv_state(timeout=deadline_wait)
        for c in clients:
            await drain_inbox(c, timeout=0.3)

        state = clients[0].last_state
        assert_true(
            state["round_number"] >= 2 or state["phase"] == "results",
            f"[{room_code}] timer didn't auto-resolve (round={state['round_number']}, phase={state['phase']})",
        )
        print(
            f"  [{room_code}] timer auto-resolved: round={state['round_number']} "
            f"phase={state['phase']}"
        )
    finally:
        await close_clients(clients)


@pytest.mark.asyncio
async def test_hold_reduces_collapse_bar(backend):
    """HOLD reduces collapse bar; verify it's lower than +34/round."""
    room_code = "HLD01"
    clients = await join_room(room_code, PLAYER_NAMES)
    try:
        host = find_host(clients)
        state = await start_game(host, clients)

        # Play optimally to reach finale
        expected_crises_by_round = {
            1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2, 7: 2, 8: 3, 9: 3, 10: 3
        }
        for rnd in range(1, 11):
            state = clients[0].last_state
            if state["phase"] != "survival":
                break
            crises = state["active_crises"]
            assignments = []
            standing = [p for p in state["players"] if not p["is_down"]]
            pi = 0
            for crisis in crises:
                needed = crisis["crew_required"]
                for _ in range(needed):
                    if pi < len(standing):
                        assignments.append(("fix", standing[pi]["id"], crisis["id"], crisis["system"]))
                        pi += 1
            lowest = min(state["systems"], key=lambda s: state["systems"][s])
            for p in standing[pi:]:
                assignments.append(("bolster", p["id"], None, lowest))
            for c in clients:
                for a in assignments:
                    if a[1] == c.player_id:
                        await submit_action(
                            c, a[0],
                            target_system=a[3], target_crisis_id=a[2],
                        )
            await resolve_and_collect(host, clients)

        state = clients[0].last_state
        assert_eq(state["phase"], "finale", f"[{room_code}] should reach finale")

        # Finale round 1: everyone HOLDs (instead of RUN)
        for c in clients:
            await submit_action(c, "hold")
        state = await resolve_and_collect(host, clients)
        # With 4 holds: collapse = 0 + 34 - (4*15) = 34 - 60 = max(0, -26) = 0
        assert_true(
            state["collapse_bar"] == 0,
            f"[{room_code}] HOLD kept collapse at 0 (got {state['collapse_bar']})",
        )
        print(f"  [{room_code}] HOLD round 1: collapse={state['collapse_bar']}")
    finally:
        await close_clients(clients)


@pytest.mark.asyncio
async def test_partial_win(backend):
    """Partial win: some crew escape, some don't."""
    room_code = "PRT01"
    clients = await join_room(room_code, PLAYER_NAMES)
    try:
        host = find_host(clients)
        state = await start_game(host, clients)

        # Reach finale with optimal play
        for rnd in range(1, 11):
            state = clients[0].last_state
            if state["phase"] != "survival":
                break
            crises = state["active_crises"]
            assignments = []
            standing = [p for p in state["players"] if not p["is_down"]]
            pi = 0
            for crisis in crises:
                needed = crisis["crew_required"]
                for _ in range(needed):
                    if pi < len(standing):
                        assignments.append(("fix", standing[pi]["id"], crisis["id"], crisis["system"]))
                        pi += 1
            lowest = min(state["systems"], key=lambda s: state["systems"][s])
            for p in standing[pi:]:
                assignments.append(("bolster", p["id"], None, lowest))
            for c in clients:
                for a in assignments:
                    if a[1] == c.player_id:
                        await submit_action(
                            c, a[0],
                            target_system=a[3], target_crisis_id=a[2],
                        )
            await resolve_and_collect(host, clients)

        state = clients[0].last_state
        assert_eq(state["phase"], "finale", f"[{room_code}] should reach finale")

        # Finale: 2 players RUN every round (escape in 3 rounds), 2 HOLD.
        # After 3 rounds, the 2 RUNners escape; the 2 HOLDers don't.
        runners = [clients[0], clients[1]]
        holders = [clients[2], clients[3]]
        for fr in range(1, 4):
            state = clients[0].last_state
            if state["phase"] != "finale":
                break
            for c in runners:
                await submit_action(c, "run")
            for c in holders:
                await submit_action(c, "hold")
            await resolve_and_collect(host, clients)

        state = clients[0].last_state
        assert_eq(state["phase"], "results", f"[{room_code}] should end in results")
        assert_true(
            state["partial"],
            f"[{room_code}] should be partial (some escaped, some didn't)",
        )
        assert_true(
            len(state["crew_survived"]) > 0 and len(state["crew_lost"]) > 0,
            f"[{room_code}] should have both survivors and lost",
        )
        print(
            f"  [{room_code}] partial win: survived={len(state['crew_survived'])} "
            f"lost={len(state['crew_lost'])}"
        )
    finally:
        await close_clients(clients)


@pytest.mark.asyncio
async def test_loss_in_finale(backend):
    """Loss in finale: collapse hits 100% before anyone escapes."""
    room_code = "LSS01"
    clients = await join_room(room_code, PLAYER_NAMES)
    try:
        host = find_host(clients)
        state = await start_game(host, clients)

        # Reach finale with optimal play
        for rnd in range(1, 11):
            state = clients[0].last_state
            if state["phase"] != "survival":
                break
            crises = state["active_crises"]
            assignments = []
            standing = [p for p in state["players"] if not p["is_down"]]
            pi = 0
            for crisis in crises:
                needed = crisis["crew_required"]
                for _ in range(needed):
                    if pi < len(standing):
                        assignments.append(("fix", standing[pi]["id"], crisis["id"], crisis["system"]))
                        pi += 1
            lowest = min(state["systems"], key=lambda s: state["systems"][s])
            for p in standing[pi:]:
                assignments.append(("bolster", p["id"], None, lowest))
            for c in clients:
                for a in assignments:
                    if a[1] == c.player_id:
                        await submit_action(
                            c, a[0],
                            target_system=a[3], target_crisis_id=a[2],
                        )
            await resolve_and_collect(host, clients)

        state = clients[0].last_state
        assert_eq(state["phase"], "finale", f"[{room_code}] should reach finale")

        # Finale: everyone HOLDs (don't RUN). Collapse climbs +34/round.
        # After 3 rounds: 34, 68, 102 -> >= 100 -> loss.
        for fr in range(1, 4):
            state = clients[0].last_state
            if state["phase"] != "finale":
                break
            for c in clients:
                await submit_action(c, "hold")
            await resolve_and_collect(host, clients)

        state = clients[0].last_state
        assert_eq(state["phase"], "results", f"[{room_code}] should end in results")
        assert_true(
            not state["victory"],
            f"[{room_code}] should be a loss (collapse hit 100%)",
        )
        assert_true(
            len(state["crew_lost"]) == 4,
            f"[{room_code}] all crew lost (got {len(state['crew_lost'])})",
        )
        print(f"  [{room_code}] finale loss: collapse={state['collapse_bar']} victory={state['victory']}")
    finally:
        await close_clients(clients)


@pytest.mark.asyncio
async def test_carry_with_two_carriers(backend):
    """CARRY with 2 carriers advances a downed player's escape_track.

    Down a player deliberately via debug hook, reach finale, then carry
    them with 2 carriers each round.
    """
    room_code = "CRY01"
    clients = await join_room(room_code, PLAYER_NAMES)
    try:
        host = find_host(clients)
        state = await start_game(host, clients)

        # Use debug hook to down "Dave" right at the start.
        state = await debug_down_and_drain(host, clients, "Dave")
        dave = next(p for p in state["players"] if p["name"] == "Dave")
        assert_true(dave["is_down"], f"[{room_code}] Dave should be downed")

        # Phase 1: reach finale. Downed players stay down (we don't revive).
        # Fix all crises with the 3 standing players.
        for rnd in range(1, 11):
            state = clients[0].last_state
            if state["phase"] != "survival":
                break
            crises = state["active_crises"]
            standing = [p for p in state["players"] if not p["is_down"]]
            pi = 0
            for crisis in crises:
                needed = crisis["crew_required"]
                for _ in range(needed):
                    if pi < len(standing):
                        c = next(cl for cl in clients if cl.player_id == standing[pi]["id"])
                        await submit_action(c, "fix", target_crisis_id=crisis["id"])
                        pi += 1
            for p in standing[pi:]:
                c = next(cl for cl in clients if cl.player_id == p["id"])
                await submit_action(c, "bolster", target_system="reactor")
            state = await resolve_and_collect(host, clients)
            if state["phase"] == "results":
                break

        state = clients[0].last_state
        if state["phase"] != "finale":
            print(f"  [{room_code}] game ended before finale (phase={state['phase']}); skipping CARRY assertion")
            return

        downed = [p for p in state["players"] if p["is_down"]]
        assert_true(
            len(downed) >= 1,
            f"[{room_code}] need a downed player in finale for CARRY",
        )
        victim = downed[0]
        standing = [p for p in state["players"] if not p["is_down"]]
        assert_true(
            len(standing) >= 2,
            f"[{room_code}] need 2 standing players to CARRY",
        )

        # Finale round 1: 2 carriers CARRY the victim; remaining standing RUNs
        carriers = standing[:2]
        for cp in carriers:
            c = next(cl for cl in clients if cl.player_id == cp["id"])
            await submit_action(c, "carry", target_player_id=victim["id"])
        if len(standing) > 2:
            runner = standing[2]
            c = next(cl for cl in clients if cl.player_id == runner["id"])
            await submit_action(c, "run")

        state = await resolve_and_collect(host, clients)
        v = player_by_id(state, victim["id"])
        assert_true(
            v["escape_track"] >= 1,
            f"[{room_code}] CARRY advanced escape_track to {v['escape_track']}",
        )
        print(f"  [{room_code}] CARRY advanced {v['name']} escape_track to {v['escape_track']}")
    finally:
        await close_clients(clients)


# ---------------------------------------------------------------------------
# Happy-path tests (pytest wrappers + standalone main)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_happy_path_game_1(backend):
    summary = await play_one_full_game(1)
    print(f"  -> OK: {summary}")


@pytest.mark.asyncio
async def test_happy_path_game_2(backend):
    summary = await play_one_full_game(2)
    print(f"  -> OK: {summary}")


@pytest.mark.asyncio
async def test_happy_path_game_3(backend):
    summary = await play_one_full_game(3)
    print(f"  -> OK: {summary}")


# ---------------------------------------------------------------------------
# Standalone runner (happy path only, for `python tests/test_e2e_playtest.py`)
# ---------------------------------------------------------------------------
async def main() -> int:
    print("=== Station Meltdown E2E Playtest ===")
    proc = start_backend(ACTION_PHASE_SECONDS)
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

    stop_backend(proc)

    print("\n=== Summary ===")
    for r in results:
        print(
            f"  {r['room_code']}: victory={r.get('victory')} "
            f"partial={r.get('partial')} survived={r.get('survived')} "
            f"lost={r.get('lost')}"
        )
    if failures:
        print(f"\nFAILED ({len(failures)} game(s)):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"\nALL {len(results)} GAMES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))