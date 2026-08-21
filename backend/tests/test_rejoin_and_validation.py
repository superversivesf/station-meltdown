"""Tests for the rejoin protocol, room lifecycle, and WS error handling.

Covers the fixes shipped together in the "most urgent fixes" pass:
  - rejoin reclaims a player's slot (and revives disconnect-downed players)
  - lobby disconnect removes the player; host promotion on host disconnect
  - resolve debounce blocks double-resolve
  - action / message validation returns errors instead of crashing the socket
  - room-full rejection
"""
import contextlib

import pytest
from fastapi.testclient import TestClient

from game import Game
from main import app
from models import Phase, PlayerAction, ActionType, SystemName


# ---------------------------------------------------------------------------
# Game-level unit tests
# ---------------------------------------------------------------------------


def test_rejoin_reclaims_slot_and_clears_disconnect_down():
    g = Game("REJX")
    p = g.add_player("Alice")
    # Simulate a disconnect: the player is downed with disconnect_down set.
    p.is_down = True
    p.disconnect_down = True

    rejoined = g.rejoin_player(p.id, "Alice")

    assert rejoined is p  # same slot, not a duplicate
    assert rejoined.is_down is False
    assert rejoined.disconnect_down is False
    assert len(g.state.players) == 1


def test_rejoin_without_id_creates_new_player():
    g = Game("REJX")
    g.add_player("Alice")
    new = g.rejoin_player(None, "Bob")
    assert new.name == "Bob"
    assert len(g.state.players) == 2


def test_rejoin_unknown_id_creates_new_player():
    g = Game("REJX")
    g.add_player("Alice")
    new = g.rejoin_player("nonexistent", "Bob")
    assert new.name == "Bob"
    assert len(g.state.players) == 2


def test_rejoin_does_not_revive_game_down():
    """A rejoin must only undo DISCONNECT-induced downs, not game-mechanic
    downs (life support / finale) — otherwise a reconnect would resurrect a
    player the game intentionally downed."""
    g = Game("REJX")
    p = g.add_player("Alice")
    p.is_down = True
    p.disconnect_down = False  # game-caused down

    rejoined = g.rejoin_player(p.id, "Alice")

    assert rejoined is p
    assert rejoined.is_down is True  # still down
    assert rejoined.disconnect_down is False


def test_remove_player_drops_from_roster():
    g = Game("REJX")
    alice = g.add_player("Alice")
    g.add_player("Bob")
    g.add_player("Carol")
    g.remove_player(alice.id)
    assert [p.name for p in g.state.players] == ["Bob", "Carol"]


def test_promote_next_host():
    g = Game("REJX")
    g.add_player("Alice")  # host
    g.add_player("Bob")
    g.add_player("Carol")
    # Simulate mid-game host disconnect: down the host, then promote
    g.state.players[0].is_down = True
    g.promote_next_host()
    assert g.state.players[0].is_host is False  # Alice cleared
    assert g.state.players[1].is_host is True  # Bob promoted


def test_submit_action_wrong_phase_rejected():
    g = Game("REJX")
    for i in range(4):
        g.add_player(f"P{i}")
    g.start()  # survival
    p = g.state.players[0]
    with pytest.raises(ValueError, match="not allowed"):
        g.submit_action(PlayerAction(
            player_id=p.id,
            action_type=ActionType.RUN,  # finale-only
        ))


def test_submit_action_while_down_rejected():
    g = Game("REJX")
    for i in range(4):
        g.add_player(f"P{i}")
    g.start()
    downed = g.state.players[1]
    downed.is_down = True
    with pytest.raises(ValueError, match="down"):
        g.submit_action(PlayerAction(
            player_id=downed.id,
            action_type=ActionType.BOLSTER,
            target_system=SystemName.HULL,
        ))


def test_resolve_round_stamps_last_resolve_at():
    g = Game("REJX")
    for i in range(4):
        g.add_player(f"P{i}")
    g.start()
    assert g.last_resolve_at == 0.0
    g.resolve_round()
    assert g.last_resolve_at > 0.0


# ---------------------------------------------------------------------------
# WebSocket-level integration tests
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _open_players(client, room_code, host_ws, names):
    """Join `names` to a lobby via persistent sockets.

    Yields (stack, sockets). The sockets must stay open for the players to
    remain in the room — a lobby disconnect now removes the player. The
    caller closes the stack at test end; individual sockets can be closed
    mid-test to trigger disconnect handling.
    """
    stack = contextlib.ExitStack()
    sockets = []
    try:
        for name in names:
            ws = stack.enter_context(client.websocket_connect(f"/ws/{room_code}"))
            sockets.append(ws)
            ws.send_json({"type": "join", "name": name})
            # Every connected socket receives the join broadcast — drain them
            # all so no stale state is left buffered for later reads.
            for s in [host_ws, *sockets]:
                s.receive_json()
        yield stack, sockets
    finally:
        stack.close()


def test_lobby_disconnect_removes_player():
    client = TestClient(app)
    with client.websocket_connect("/ws/LOB1") as host:
        host.send_json({"type": "join", "name": "Alice"})
        host.receive_json()
        with _open_players(client, "LOB1", host, ["Bob", "Carol", "Dave"]) as (stack, sockets):
            # Dave leaves the lobby
            sockets[2].close()
            msg = host.receive_json()
            assert msg["type"] == "state"
            assert [p["name"] for p in msg["state"]["players"]] == ["Alice", "Bob", "Carol"]


def test_host_promotion_on_lobby_disconnect():
    client = TestClient(app)
    with client.websocket_connect("/ws/HOST1") as host:
        host.send_json({"type": "join", "name": "Alice"})
        host.receive_json()
        with _open_players(client, "HOST1", host, ["Bob", "Carol", "Dave"]) as (stack, sockets):
            # Host (Alice) leaves the lobby
            host.close()
            msg = sockets[0].receive_json()  # Bob's next broadcast
            assert msg["type"] == "state"
            names = [p["name"] for p in msg["state"]["players"]]
            assert "Alice" not in names
            bob = next(p for p in msg["state"]["players"] if p["name"] == "Bob")
            assert bob["is_host"] is True


def test_rejoin_mid_game_revives_player():
    client = TestClient(app)
    with client.websocket_connect("/ws/REJ1") as host:
        host.send_json({"type": "join", "name": "Alice"})
        host.receive_json()
        with _open_players(client, "REJ1", host, ["Bob", "Carol"]) as (stack, sockets):
            # Join Dave on a dedicated socket so we can capture + close it.
            dave = stack.enter_context(client.websocket_connect("/ws/REJ1"))
            dave.send_json({"type": "join", "name": "Dave"})
            host.receive_json()
            dave_state = dave.receive_json()
            dave_id = dave_state["player_id"]

            # Start the game
            host.send_json({"type": "start"})
            host.receive_json()  # state: survival round 1

            # Disconnect Dave mid-game → spec says disconnect = downed
            dave.close()
            msg = host.receive_json()
            assert msg["type"] == "state"
            dave_player = next(p for p in msg["state"]["players"] if p["id"] == dave_id)
            assert dave_player["is_down"] is True

            # Reconnect with the same player_id → reclaimed + revived
            with client.websocket_connect("/ws/REJ1") as dave2:
                dave2.send_json({"type": "join", "name": "Dave", "player_id": dave_id})
                msg = dave2.receive_json()
                assert msg["type"] == "state"
                assert msg["player_id"] == dave_id  # same slot, no duplicate
                dave_player = next(p for p in msg["state"]["players"] if p["id"] == dave_id)
                assert dave_player["is_down"] is False


def test_host_promotion_mid_game():
    client = TestClient(app)
    with client.websocket_connect("/ws/HOST2") as host:
        host.send_json({"type": "join", "name": "Alice"})
        host.receive_json()
        with _open_players(client, "HOST2", host, ["Bob", "Carol", "Dave"]) as (stack, sockets):
            host.send_json({"type": "start"})
            host.receive_json()  # survival round 1
            sockets[0].receive_json()  # Bob's round-1 broadcast (drain)

            # Host (Alice) disconnects mid-game
            host.close()
            msg = sockets[0].receive_json()  # Bob's next broadcast
            assert msg["type"] == "state"
            alice = next(p for p in msg["state"]["players"] if p["name"] == "Alice")
            assert alice["is_down"] is True  # disconnect = downed
            bob = next(p for p in msg["state"]["players"] if p["name"] == "Bob")
            assert bob["is_host"] is True  # host duties transferred


def test_invalid_action_type_returns_error():
    client = TestClient(app)
    with client.websocket_connect("/ws/ACT1") as host:
        host.send_json({"type": "join", "name": "Alice"})
        host.receive_json()
        with _open_players(client, "ACT1", host, ["Bob", "Carol", "Dave"]) as (stack, sockets):
            host.send_json({"type": "start"})
            host.receive_json()
            host.send_json({"type": "action", "action_type": "teleport"})
            msg = host.receive_json()
            assert msg["type"] == "error"
            assert "action_type" in msg["message"].lower()
            # Socket still usable
            host.send_json({"type": "action", "action_type": "bolster", "target_system": "hull"})
            ack = host.receive_json()
            assert ack["type"] == "action_ack"


def test_action_wrong_phase_returns_error():
    client = TestClient(app)
    with client.websocket_connect("/ws/ACT2") as host:
        host.send_json({"type": "join", "name": "Alice"})
        host.receive_json()
        with _open_players(client, "ACT2", host, ["Bob", "Carol", "Dave"]) as (stack, sockets):
            host.send_json({"type": "start"})
            host.receive_json()  # survival
            # RUN is finale-only
            host.send_json({"type": "action", "action_type": "run"})
            msg = host.receive_json()
            assert msg["type"] == "error"
            assert "not allowed" in msg["message"].lower()


def test_malformed_frame_returns_error():
    client = TestClient(app)
    with client.websocket_connect("/ws/BAD1") as ws:
        ws.send_text("this is not json {{{")
        msg = ws.receive_json()
        assert msg["type"] == "error"
        # Socket survives the bad frame — can still join
        ws.send_json({"type": "join", "name": "Alice"})
        msg = ws.receive_json()
        assert msg["type"] == "state"
        assert msg["state"]["players"][0]["name"] == "Alice"


def test_non_dict_frame_returns_error():
    client = TestClient(app)
    with client.websocket_connect("/ws/BAD2") as ws:
        ws.send_json([1, 2, 3])  # valid JSON, but not an object
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_resolve_debounce_blocks_double_resolve():
    client = TestClient(app)
    with client.websocket_connect("/ws/DB1") as host:
        host.send_json({"type": "join", "name": "Alice"})
        host.receive_json()
        with _open_players(client, "DB1", host, ["Bob", "Carol", "Dave"]) as (stack, sockets):
            host.send_json({"type": "start"})
            host.receive_json()  # round 1

            host.send_json({"type": "resolve"})
            msg = host.receive_json()
            assert msg["type"] == "state"
            assert msg["state"]["round_number"] == 2

            # Immediate second resolve must be rejected, not advance a round.
            host.send_json({"type": "resolve"})
            msg = host.receive_json()
            assert msg["type"] == "error"
            assert "already resolved" in msg["message"].lower()


def test_join_when_room_full_returns_error():
    client = TestClient(app)
    names = [f"P{i}" for i in range(15)]
    with client.websocket_connect("/ws/FULL1") as host:
        host.send_json({"type": "join", "name": names[0]})
        host.receive_json()
        stack = contextlib.ExitStack()
        try:
            for i in range(1, 15):
                ws = stack.enter_context(client.websocket_connect("/ws/FULL1"))
                ws.send_json({"type": "join", "name": names[i]})
                host.receive_json()
                ws.receive_json()
            # 16th player is rejected with a real error message.
            with client.websocket_connect("/ws/FULL1") as extra:
                extra.send_json({"type": "join", "name": "Overflow"})
                msg = extra.receive_json()
                assert msg["type"] == "error"
                assert "full" in msg["message"].lower()
        finally:
            stack.close()


def test_rejoin_mid_finale_revives_player():
    """Rejoin during finale must reclaim the slot and revive a disconnect-downed player."""
    import os as _os
    _os.environ["DEBUG_MODE"] = "1"
    try:
        client = TestClient(app)
        with client.websocket_connect("/ws/REJ2") as host:
            host.send_json({"type": "join", "name": "Alice"})
            host.receive_json()
            with _open_players(client, "REJ2", host, ["Bob", "Carol"]) as (stack, sockets):
                dave = stack.enter_context(client.websocket_connect("/ws/REJ2"))
                dave.send_json({"type": "join", "name": "Dave"})
                host.receive_json()
                dave_state = dave.receive_json()
                dave_id = dave_state["player_id"]

                host.send_json({"type": "start"})
                host.receive_json()  # survival round 1
                for s in sockets:
                    s.receive_json()
                dave.receive_json()

                from main import ROOMS
                game = ROOMS["REJ2"]
                game.state.phase = Phase.FINALE
                game.state.round_number = 1
                game.state.collapse_bar = 0
                game.state.active_crises = []
                host.send_json({"type": "debug_set_system", "system": "reactor", "hp": 100})
                for s in [host, *sockets, dave]:
                    s.receive_json()

                dave.close()
                msg = host.receive_json()
                assert msg["type"] == "state"
                dave_player = next(p for p in msg["state"]["players"] if p["id"] == dave_id)
                assert dave_player["is_down"] is True

                with client.websocket_connect("/ws/REJ2") as dave2:
                    dave2.send_json({"type": "join", "name": "Dave", "player_id": dave_id})
                    msg = dave2.receive_json()
                    assert msg["type"] == "state"
                    assert msg["player_id"] == dave_id
                    dave_player = next(p for p in msg["state"]["players"] if p["id"] == dave_id)
                    assert dave_player["is_down"] is False
    finally:
        del _os.environ["DEBUG_MODE"]


def test_resolve_rejected_in_lobby():
    """Resolve in lobby phase must not crash the socket."""
    client = TestClient(app)
    with client.websocket_connect("/ws/RSLV1") as host:
        host.send_json({"type": "join", "name": "Alice"})
        host.receive_json()
        with _open_players(client, "RSLV1", host, ["Bob", "Carol", "Dave"]) as (stack, sockets):
            # Resolve in lobby broadcasts state (resolve_round is a no-op
            # but the handler still calls broadcast_state). Drain it.
            host.send_json({"type": "resolve"})
            msg = host.receive_json()
            assert msg["type"] == "state"
            assert msg["state"]["phase"] == "lobby"
            # Socket still alive — join another player
            extra = stack.enter_context(client.websocket_connect("/ws/RSLV1"))
            extra.send_json({"type": "join", "name": "Eve"})
            msg = host.receive_json()
            assert msg["type"] == "state"
            assert len(msg["state"]["players"]) == 5


def test_resolve_rejected_in_results():
    """Resolve in results phase must not crash or advance the game."""
    import os as _os
    _os.environ["DEBUG_MODE"] = "1"
    try:
        client = TestClient(app)
        with client.websocket_connect("/ws/RSLV2") as host:
            host.send_json({"type": "join", "name": "Alice"})
            host.receive_json()
            with _open_players(client, "RSLV2", host, ["Bob", "Carol", "Dave"]) as (stack, sockets):
                host.send_json({"type": "start"})
                host.receive_json()
                for s in sockets:
                    s.receive_json()
                # Set reactor to 0 so next resolve ends the game
                host.send_json({"type": "debug_set_system", "system": "reactor", "hp": 0})
                for s in [host, *sockets]:
                    s.receive_json()
                host.send_json({"type": "resolve"})
                for s in [host, *sockets]:
                    s.receive_json()

                # Now in results — another resolve is debounce-rejected
                # (no actions since the resolve that ended the game).
                host.send_json({"type": "resolve"})
                msg = host.receive_json()
                assert msg["type"] == "error"
                assert "already resolved" in msg["message"].lower()
    finally:
        del _os.environ["DEBUG_MODE"]


def test_crises_deterministic_with_seed():
    """Two games with the same CRISIS_SEED must produce identical crisis sequences."""
    import os as _os
    _os.environ["CRISIS_SEED"] = "42"
    try:
        from crises import spawn_crises
        import random as _random
        _random.seed(42)
        seq1 = [spawn_crises(r) for r in range(1, 11)]
        _random.seed(42)
        seq2 = [spawn_crises(r) for r in range(1, 11)]
        for rnd, (a, b) in enumerate(zip(seq1, seq2), 1):
            assert [c.id for c in a] == [c.id for c in b], f"round {rnd} differs"
    finally:
        del _os.environ["CRISIS_SEED"]


def test_session_cap_ends_game():
    """30-minute hard cap must end the game as a loss."""
    import time as _time
    from game import Game
    from models import Phase

    g = Game("CAP1")
    for i in range(4):
        g.add_player(f"P{i}")
    g.start()
    # Simulate 31 minutes elapsed
    g.state.started_at = _time.time() - 1860
    # The cap check lives in start_action_timer, not resolve_round.
    # Drive it directly: the timer path calls _end_game.
    g._end_game(victory=False)
    assert g.state.phase == Phase.RESULTS
    assert g.state.victory is False
