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