import pytest
from models import (
    SystemName, Phase, ActionType, Crisis, Player, PlayerAction, GameState
)

def test_system_name_values():
    assert SystemName.REACTOR == "reactor"
    assert SystemName.LIFE_SUPPORT == "life_support"
    assert SystemName.MED_BAY == "med_bay"
    assert SystemName.HULL == "hull"
    assert SystemName.COMMS == "comms"
    assert SystemName.SHIELDS == "shields"

def test_phase_values():
    assert Phase.LOBBY == "lobby"
    assert Phase.SURVIVAL == "survival"
    assert Phase.FINALE == "finale"
    assert Phase.RESULTS == "results"

def test_action_type_values():
    assert ActionType.FIX == "fix"
    assert ActionType.BOLSTER == "bolster"
    assert ActionType.REVIVE == "revive"
    assert ActionType.RUN == "run"
    assert ActionType.CARRY == "carry"
    assert ActionType.HOLD == "hold"

def test_crisis_model():
    c = Crisis(
        id="coolant_leak",
        name="Coolant Leak",
        description="Coolant spraying from reactor coupling",
        system=SystemName.REACTOR,
        drain_rate=3,
        crew_required=2,
        tier=1,
        weight=10,
    )
    assert c.id == "coolant_leak"
    assert c.system == SystemName.REACTOR
    assert c.crew_required == 2

def test_player_model():
    p = Player(name="Alice", is_host=True)
    assert p.name == "Alice"
    assert p.is_host is True
    assert p.is_down is False
    assert p.escape_track == 0

def test_player_action_validation():
    a = PlayerAction(
        player_id="p1",
        action_type=ActionType.FIX,
        target_system=SystemName.REACTOR,
        target_crisis_id="coolant_leak",
    )
    assert a.action_type == ActionType.FIX
    assert a.target_crisis_id == "coolant_leak"

def test_player_action_bolster_has_no_crisis():
    a = PlayerAction(
        player_id="p1",
        action_type=ActionType.BOLSTER,
        target_system=SystemName.HULL,
    )
    assert a.target_crisis_id is None

def test_game_state_defaults():
    gs = GameState(room_code="ABCD")
    assert gs.room_code == "ABCD"
    assert gs.phase == Phase.LOBBY
    assert gs.round_number == 0
    assert gs.collapse_bar == 0
    assert gs.players == []
    assert gs.active_crises == []
    # All systems start at 100
    assert gs.systems[SystemName.REACTOR] == 100
    assert gs.systems[SystemName.SHIELDS] == 100