import pytest
from game import Game
from models import Phase


def test_new_game_starts_in_lobby():
    g = Game("ABCD")
    state = g.get_state()
    assert state.room_code == "ABCD"
    assert state.phase == Phase.LOBBY
    assert state.round_number == 0
    assert len(state.players) == 0


def test_add_player():
    g = Game("ABCD")
    p = g.add_player("Alice")
    assert p.name == "Alice"
    assert p.id  # non-empty ID
    state = g.get_state()
    assert len(state.players) == 1
    assert state.players[0].name == "Alice"


def test_first_player_is_host():
    g = Game("ABCD")
    p1 = g.add_player("Alice")
    p2 = g.add_player("Bob")
    assert p1.is_host is True
    assert p2.is_host is False


def test_is_host():
    g = Game("ABCD")
    p = g.add_player("Alice")
    assert g.is_host(p.id) is True
    assert g.is_host("nonexistent") is False


def test_start_transitions_to_survival():
    g = Game("ABCD")
    g.add_player("Alice")
    g.add_player("Bob")
    g.add_player("Carol")
    g.add_player("Dave")
    g.start()
    state = g.get_state()
    assert state.phase == Phase.SURVIVAL
    assert state.round_number == 1
    # Round 1 spawns 1 crisis
    assert len(state.active_crises) == 1


def test_start_requires_minimum_players():
    g = Game("ABCD")
    g.add_player("Alice")
    g.add_player("Bob")
    g.add_player("Carol")
    with pytest.raises(ValueError, match="minimum 4 players"):
        g.start()


def test_start_requires_lobby_phase():
    g = Game("ABCD")
    for i in range(4):
        g.add_player(f"Player{i}")
    g.start()
    with pytest.raises(ValueError, match="can only start from lobby"):
        g.start()