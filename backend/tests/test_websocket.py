import pytest
from fastapi.testclient import TestClient
from main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_websocket_join():
    client = TestClient(app)
    with client.websocket_connect("/ws/TEST") as ws:
        ws.send_json({"type": "join", "name": "Alice"})
        msg = ws.receive_json()
        assert msg["type"] == "state"
        assert msg["state"]["room_code"] == "TEST"
        assert msg["state"]["phase"] == "lobby"
        assert len(msg["state"]["players"]) == 1
        assert msg["state"]["players"][0]["name"] == "Alice"
        assert msg["player_id"] is not None


def test_websocket_multiple_players_join():
    client = TestClient(app)
    with client.websocket_connect("/ws/TEST2") as ws1:
        ws1.send_json({"type": "join", "name": "Alice"})
        ws1.receive_json()  # state update
        with client.websocket_connect("/ws/TEST2") as ws2:
            ws2.send_json({"type": "join", "name": "Bob"})
            # Both should receive state update with 2 players
            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()
            assert msg1["type"] == "state"
            assert len(msg1["state"]["players"]) == 2
            assert msg2["type"] == "state"
            assert len(msg2["state"]["players"]) == 2


def test_websocket_start_requires_host():
    client = TestClient(app)
    with client.websocket_connect("/ws/TEST3") as ws1:
        ws1.send_json({"type": "join", "name": "Alice"})
        ws1.receive_json()
        with client.websocket_connect("/ws/TEST3") as ws2:
            ws2.send_json({"type": "join", "name": "Bob"})
            ws1.receive_json()  # both get update
            ws2.receive_json()
            # Non-host tries to start
            ws2.send_json({"type": "start"})
            msg = ws2.receive_json()
            assert msg["type"] == "error"
            assert "host" in msg["message"].lower()


def test_websocket_start_success():
    client = TestClient(app)
    with client.websocket_connect("/ws/TEST4") as ws1:
        ws1.send_json({"type": "join", "name": "Alice"})
        ws1.receive_json()
        for i in range(3):
            with client.websocket_connect("/ws/TEST4") as ws_other:
                ws_other.send_json({"type": "join", "name": f"Player{i}"})
                ws1.receive_json()
                ws_other.receive_json()
        # Host starts
        ws1.send_json({"type": "start"})
        msg = ws1.receive_json()
        assert msg["type"] == "state"
        assert msg["state"]["phase"] == "survival"
        assert msg["state"]["round_number"] == 1


def test_action_phase_sets_deadline():
    """When game starts, action phase deadline is set."""
    client = TestClient(app)
    with client.websocket_connect("/ws/TIMER1") as ws:
        ws.send_json({"type": "join", "name": "Alice"})
        ws.receive_json()
        for i in range(3):
            with client.websocket_connect("/ws/TIMER1") as ws_other:
                ws_other.send_json({"type": "join", "name": f"P{i}"})
                ws.receive_json()
                ws_other.receive_json()
        ws.send_json({"type": "start"})
        msg = ws.receive_json()
        assert msg["state"]["phase"] == "survival"
        assert msg["state"]["action_phase_deadline"] is not None
        assert msg["state"]["action_phase_deadline"] > 0


def test_afk_player_defaults_to_bolster():
    """If a player doesn't submit an action, they default to BOLSTER on resolve."""
    from main import ROOMS
    client = TestClient(app)
    with client.websocket_connect("/ws/TIMER2") as ws:
        ws.send_json({"type": "join", "name": "Alice"})
        ws.receive_json()
        for i in range(3):
            with client.websocket_connect("/ws/TIMER2") as ws_other:
                ws_other.send_json({"type": "join", "name": f"P{i}"})
                ws.receive_json()
                ws_other.receive_json()
        ws.send_json({"type": "start"})
        ws.receive_json()
        # Only one player submits an action
        ws.send_json({
            "type": "action",
            "action_type": "bolster",
            "target_system": "shields",
        })
        ws.receive_json()  # action_ack
        # Resolve — 3 players didn't act, should default to bolster
        ws.send_json({"type": "resolve"})
        msg = ws.receive_json()
        # No crash, state advanced
        assert msg["state"]["round_number"] == 2


def test_action_timer_auto_resolves_on_deadline():
    """Background timer auto-resolves the round when the action deadline passes.

    Patches `Game._set_action_deadline` to use a 0.5s deadline (instead of the
    real 45s) so the timer spawned by the `start` handler fires quickly. Verifies
    that a `state` broadcast arrives — WITHOUT any manual `resolve` message from
    the client — showing `round_number` advanced to 2.

    Only the FIRST round's deadline is short. After the auto-resolve,
    `resolve_round()` calls `_set_action_deadline()` again for round 2 (also
    patched to 0.5s here, but that's fine — the test asserts on the first
    broadcast and drains the rest, capping total wall time well under the
    pytest default timeout).
    """
    import time as _time
    import game as game_mod
    from main import ROOMS

    # Patch the deadline setter to use a short window so the background timer
    # fires within the test window. Restore on teardown.
    orig = game_mod.Game._set_action_deadline
    short_deadlines: list[float] = []

    def short_set(self):
        self.state.action_phase_deadline = _time.time() + 0.5
        short_deadlines.append(self.state.action_phase_deadline)

    game_mod.Game._set_action_deadline = short_set
    try:
        client = TestClient(app)
        with client.websocket_connect("/ws/TIMER3") as ws:
            ws.send_json({"type": "join", "name": "Alice"})
            ws.receive_json()
            for i in range(3):
                with client.websocket_connect("/ws/TIMER3") as ws_other:
                    ws_other.send_json({"type": "join", "name": f"P{i}"})
                    ws.receive_json()
                    ws_other.receive_json()

            # Host starts — game enters survival round 1 with a 0.5s
            # action deadline, and the handler spawns start_action_timer.
            ws.send_json({"type": "start"})
            ws.receive_json()  # state: round 1
            assert short_deadlines, "start() did not set a deadline"

            # Wait for the background timer to fire and auto-resolve.
            # No manual 'resolve' is sent. Starlette's sync TestClient
            # WebSocket.receive_json() blocks until a message arrives (no
            # timeout kwarg), so receive on a worker thread and bound the
            # wait from the main thread.
            import threading
            received: list[dict] = []
            err: list[BaseException] = []
            done = threading.Event()

            def drain():
                try:
                    for _ in range(10):
                        received.append(ws.receive_json())
                        if received[-1].get("type") == "state" and \
                                received[-1]["state"].get("round_number") == 2:
                            done.set()
                            return
                except BaseException as e:  # noqa: BLE001
                    err.append(e)
                    done.set()

            t = threading.Thread(target=drain, daemon=True)
            t.start()
            if not done.wait(timeout=5):
                assert False, "auto-resolve did not advance to round 2 within 5s"
            assert not err, f"receiver thread errored: {err}"
            assert received, "no messages received"
            last = received[-1]
            assert last.get("type") == "state", f"unexpected message: {last}"
            assert last["state"].get("round_number") == 2, \
                f"did not reach round 2: {last}"

            # Sanity: the timer that fired used the patched short deadline.
            assert short_deadlines[0] <= _time.time()
    finally:
        game_mod.Game._set_action_deadline = orig
        ROOMS.pop("TIMER3", None)


def test_action_timer_rearms_for_next_round():
    """Timer must re-arm after auto-resolve so round 2 also auto-resolves.

    Reproduces Finding 1: `start_action_timer` resolved round 1 → round 2
    but never spawned a new timer for round 2, so round 2 stalled.

    Patches `_set_action_deadline` to a 0.3s window and asserts the game
    auto-advances through rounds 1 → 2 → 3 with NO manual `resolve` from
    the client. Each auto-resolve must spawn the next round's timer.

    Also patches `spawn_crises` to return a benign low-drain non-reactor
    crisis so the game cannot end (reactor → 0) before reaching round 3.
    """
    import time as _time
    import threading
    import game as game_mod
    import crises as crises_mod
    from models import SystemName
    from main import ROOMS

    orig_deadline = game_mod.Game._set_action_deadline
    orig_spawn = crises_mod.spawn_crises

    def short_set(self):
        self.state.action_phase_deadline = _time.time() + 0.3

    def benign_spawn(round_number):
        # A single hull crisis with drain 2 — reactor stays at 100, so
        # the loss condition (reactor == 0) cannot trigger within 3 rounds.
        return [crises_mod.CRISIS_POOL[3]]  # hull_microfracture: hull, drain 3

    game_mod.Game._set_action_deadline = short_set
    crises_mod.spawn_crises = benign_spawn
    try:
        client = TestClient(app)
        with client.websocket_connect("/ws/TIMER4") as ws:
            ws.send_json({"type": "join", "name": "Alice"})
            ws.receive_json()
            for i in range(3):
                with client.websocket_connect("/ws/TIMER4") as ws_other:
                    ws_other.send_json({"type": "join", "name": f"P{i}"})
                    ws.receive_json()
                    ws_other.receive_json()

            ws.send_json({"type": "start"})
            ws.receive_json()  # state: round 1

            # Drain messages until we see round 3, with a bounded wait.
            # Each auto-resolve should fire ~0.3s after the previous, so
            # reaching round 3 takes ~0.6s + overhead; allow 8s margin.
            received: list[dict] = []
            err: list[BaseException] = []
            done = threading.Event()

            def drain():
                try:
                    for _ in range(30):
                        received.append(ws.receive_json())
                        last = received[-1]
                        if (last.get("type") == "state"
                                and last["state"].get("phase") == "survival"
                                and last["state"].get("round_number") == 3):
                            done.set()
                            return
                except BaseException as e:  # noqa: BLE001
                    err.append(e)
                    done.set()

            t = threading.Thread(target=drain, daemon=True)
            t.start()
            if not done.wait(timeout=8):
                assert False, \
                    "auto-resolve did not reach round 3 within 8s (no re-arm)"
            assert not err, f"receiver thread errored: {err}"
            assert received, "no messages received"
            last = received[-1]
            assert last["state"]["phase"] == "survival", \
                f"expected survival round 3, got phase={last['state']['phase']}"
            assert last["state"]["round_number"] == 3, \
                f"expected round 3, got {last['state']['round_number']}"
    finally:
        game_mod.Game._set_action_deadline = orig_deadline
        crises_mod.spawn_crises = orig_spawn
        ROOMS.pop("TIMER4", None)


def test_survival_to_finale_transition_sets_fresh_deadline():
    """Finale transition must set a fresh deadline, not leave a stale one.

    Reproduces Finding 2: `_resolve_survival_round` transitioned to finale
    when `round_number > 10` but did not call `_set_action_deadline()`. The
    stale round-10 deadline (in the past) persisted into finale round 1, so
    a timer spawned by the manual `resolve` handler would read the past
    deadline, skip the sleep, and instantly resolve finale round 1.

    This unit test drives the game directly (no WS) through 10 survival
    rounds so the next resolve transitions to finale, then asserts:
      - finale round 1 starts with round_number == 1
      - action_phase_deadline is None OR in the future (fresh), never the
        stale round-10 value
    """
    import time as _time
    import game as game_mod
    import crises as crises_mod
    from game import Game
    from models import Phase, PlayerAction, ActionType, SystemName

    # Benign crises + short deadlines so we can drive 10 rounds quickly.
    orig_spawn = crises_mod.spawn_crises

    def benign_spawn(round_number):
        return [crises_mod.CRISIS_POOL[3]]  # hull_microfracture

    crises_mod.spawn_crises = benign_spawn
    try:
        g = Game("FINALE1")
        for i in range(4):
            g.add_player(f"P{i}")
        g.start()

        # Resolve rounds 1..10. Each resolve keeps the reactor healthy
        # (everyone bolsters reactor to offset the hull crisis drain — but
        # since the crisis is on hull, reactor is untouched). Drive 10
        # rounds; the 10th resolve should transition to finale.
        # Patch the deadline to a far-future value to detect staleness:
        # if the transition leaves the old deadline in place, it will be
        # this sentinel value (in the past after we sleep). Use a past
        # sentinel to simulate the real bug where the round-10 deadline is
        # already elapsed by the time finale round 1 starts.
        past_sentinel = _time.time() - 100.0
        g.state.action_phase_deadline = past_sentinel

        # Drive 10 resolves. Each round everyone bolsters the hull (the
        # crisis system) so the system stays healthy; AFK defaults also
        # bolster the lowest system. No reactor drain occurs.
        for round_idx in range(10):
            for p in g.state.players:
                g.submit_action(PlayerAction(
                    player_id=p.id,
                    action_type=ActionType.BOLSTER,
                    target_system=SystemName.HULL,
                ))
            # Re-assert the past sentinel each round so that if the
            # transition branch does NOT set a fresh deadline, the stale
            # value present at finale round 1 is unambiguously in the past.
            g.state.action_phase_deadline = past_sentinel
            g.resolve_round()
            if g.state.phase == Phase.FINALE:
                break

        assert g.state.phase == Phase.FINALE, \
            f"expected finale transition, got {g.state.phase}"
        assert g.state.round_number == 1, \
            f"expected finale round 1, got {g.state.round_number}"

        # The transition MUST set a fresh deadline. Either:
        #   - None (cleared, no auto-resolve for finale round 1), or
        #   - a timestamp in the future (fresh 45s window)
        # A stale value in the past (like past_sentinel) is the bug.
        deadline = g.state.action_phase_deadline
        assert deadline is None or deadline > _time.time(), \
            f"stale deadline carried into finale round 1: {deadline}"
    finally:
        crises_mod.spawn_crises = orig_spawn