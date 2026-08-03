import pytest
from game import Game
from models import Phase, PlayerAction, ActionType, SystemName


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


def make_game_with_players(n=4):
    g = Game("TEST")
    for i in range(n):
        g.add_player(f"Player{i}")
    g.start()
    return g


def test_submit_action_stores_pending():
    g = make_game_with_players(4)
    p = g.state.players[0]
    action = PlayerAction(
        player_id=p.id,
        action_type=ActionType.BOLSTER,
        target_system=SystemName.REACTOR,
    )
    g.submit_action(action)
    assert len(g.state.pending_actions) == 1
    assert g.state.pending_actions[0].player_id == p.id


def test_resolve_bolster_adds_health():
    g = make_game_with_players(4)
    g.state.active_crises = []  # isolate bolster logic from crisis drain
    p = g.state.players[0]
    g.state.systems[SystemName.HULL] = 50
    g.submit_action(PlayerAction(
        player_id=p.id,
        action_type=ActionType.BOLSTER,
        target_system=SystemName.HULL,
    ))
    for other in g.state.players[1:]:
        g.submit_action(PlayerAction(
            player_id=other.id,
            action_type=ActionType.BOLSTER,
            target_system=SystemName.COMMS,
        ))
    g.resolve_round()
    assert g.state.systems[SystemName.HULL] == 55  # 50 + 5


def test_resolve_bolster_caps_at_100():
    g = make_game_with_players(4)
    p = g.state.players[0]
    g.state.systems[SystemName.HULL] = 98
    g.submit_action(PlayerAction(
        player_id=p.id,
        action_type=ActionType.BOLSTER,
        target_system=SystemName.HULL,
    ))
    g.resolve_round()
    assert g.state.systems[SystemName.HULL] == 100  # capped


def test_resolve_fix_with_enough_crew_stops_drain():
    g = make_game_with_players(4)
    # Round 1 spawns 1 crisis; find it
    crisis = g.state.active_crises[0]
    crew_needed = crisis.crew_required
    # Submit FIX actions from enough players
    for i in range(crew_needed):
        g.submit_action(PlayerAction(
            player_id=g.state.players[i].id,
            action_type=ActionType.FIX,
            target_system=crisis.system,
            target_crisis_id=crisis.id,
        ))
    initial_health = g.state.systems[crisis.system]
    g.resolve_round()
    # System should NOT have drained (crisis was fixed)
    assert g.state.systems[crisis.system] == initial_health


def test_resolve_fix_with_insufficient_crew_drains():
    g = make_game_with_players(4)
    # Force a tier-1 crisis with crew_required=2 (most tier-1 crises need 1)
    from crises import CRISIS_POOL
    two_crew_crisis = next(
        c for c in CRISIS_POOL
        if c.tier == 1 and c.crew_required == 2
    )
    forced = two_crew_crisis.model_copy()
    g.state.active_crises = [forced]
    crisis = forced
    # Only 1 player tries to FIX (needs 2)
    g.submit_action(PlayerAction(
        player_id=g.state.players[0].id,
        action_type=ActionType.FIX,
        target_system=crisis.system,
        target_crisis_id=crisis.id,
    ))
    # Other players bolster a non-crisis system so they don't mask the drain
    bolster_target = next(s for s in SystemName if s != crisis.system)
    for other in g.state.players[1:]:
        g.submit_action(PlayerAction(
            player_id=other.id,
            action_type=ActionType.BOLSTER,
            target_system=bolster_target,
        ))
    initial_health = g.state.systems[crisis.system]
    g.resolve_round()
    # System should have drained (not enough crew)
    assert g.state.systems[crisis.system] == initial_health - crisis.drain_rate


def test_resolve_unaddressed_crisis_drains():
    g = make_game_with_players(4)
    crisis = g.state.active_crises[0]
    # No one fixes it — everyone bolsters something else
    for p in g.state.players:
        g.submit_action(PlayerAction(
            player_id=p.id,
            action_type=ActionType.BOLSTER,
            target_system=SystemName.SHIELDS,
        ))
    initial_health = g.state.systems[crisis.system]
    g.resolve_round()
    assert g.state.systems[crisis.system] == initial_health - crisis.drain_rate


def test_resolve_clears_pending_actions():
    g = make_game_with_players(4)
    p = g.state.players[0]
    g.submit_action(PlayerAction(
        player_id=p.id,
        action_type=ActionType.BOLSTER,
        target_system=SystemName.REACTOR,
    ))
    g.resolve_round()
    assert len(g.state.pending_actions) == 0


def test_resolve_advances_round_and_spawns_new_crises():
    g = make_game_with_players(4)
    g.resolve_round()
    assert g.state.round_number == 2
    assert len(g.state.active_crises) >= 1  # round 2 spawns 1


def test_reactor_zero_triggers_loss():
    g = make_game_with_players(4)
    g.state.systems[SystemName.REACTOR] = 1
    crisis = g.state.active_crises[0]
    if crisis.system != SystemName.REACTOR:
        # Force a reactor crisis
        from crises import CRISIS_POOL
        reactor_crisis = [c for c in CRISIS_POOL if c.system == SystemName.REACTOR][0]
        g.state.active_crises = [reactor_crisis]
        crisis = reactor_crisis
    # No one fixes it
    for p in g.state.players:
        g.submit_action(PlayerAction(
            player_id=p.id,
            action_type=ActionType.BOLSTER,
            target_system=SystemName.SHIELDS,
        ))
    g.resolve_round()
    assert g.state.phase == Phase.RESULTS
    assert g.state.victory is False


def test_life_support_zero_downs_crew():
    g = make_game_with_players(4)
    g.state.systems[SystemName.LIFE_SUPPORT] = 0
    # Resolve round — life support at 0 should down a crew member
    for p in g.state.players:
        g.submit_action(PlayerAction(
            player_id=p.id,
            action_type=ActionType.BOLSTER,
            target_system=SystemName.SHIELDS,
        ))
    g.resolve_round()
    downed = [p for p in g.state.players if p.is_down]
    assert len(downed) >= 1


def test_shields_zero_degrades_all_systems():
    g = make_game_with_players(4)
    g.state.systems[SystemName.SHIELDS] = 0
    # Record all system healths
    initial = {s: g.state.systems[s] for s in SystemName}
    for p in g.state.players:
        g.submit_action(PlayerAction(
            player_id=p.id,
            action_type=ActionType.BOLSTER,
            target_system=SystemName.SHIELDS,
        ))
    g.resolve_round()
    # All systems except shields (which we bolstered) should degrade by 2
    for s in SystemName:
        if s == SystemName.SHIELDS:
            continue
        # May also be drained by crisis — just check it dropped by at least 2
        assert g.state.systems[s] <= initial[s] - 2


def test_revive_brings_downed_player_back():
    g = make_game_with_players(4)
    # Down a player
    downed_p = g.state.players[1]
    downed_p.is_down = True
    g.state.systems[SystemName.MED_BAY] = 50
    reviver = g.state.players[0]
    g.submit_action(PlayerAction(
        player_id=reviver.id,
        action_type=ActionType.REVIVE,
        target_player_id=downed_p.id,
    ))
    g.resolve_round()
    assert downed_p.is_down is False


def test_revive_requires_med_bay_above_zero():
    g = make_game_with_players(4)
    downed_p = g.state.players[1]
    downed_p.is_down = True
    g.state.systems[SystemName.MED_BAY] = 0
    reviver = g.state.players[0]
    g.submit_action(PlayerAction(
        player_id=reviver.id,
        action_type=ActionType.REVIVE,
        target_player_id=downed_p.id,
    ))
    for other in g.state.players[2:]:
        g.submit_action(PlayerAction(
            player_id=other.id,
            action_type=ActionType.BOLSTER,
            target_system=SystemName.COMMS,
        ))
    g.resolve_round()
    assert downed_p.is_down is True  # still down, med bay offline


def test_all_crew_downed_triggers_loss():
    g = make_game_with_players(4)
    for p in g.state.players:
        p.is_down = True
    g.resolve_round()
    assert g.state.phase == Phase.RESULTS
    assert g.state.victory is False


# ---------------------------------------------------------------------------
# Finale phase tests
# ---------------------------------------------------------------------------

def _make_finale_game(n=4):
    """Create a game and transition it to finale phase for testing."""
    g = make_game_with_players(n)
    g.state.phase = Phase.FINALE
    g.state.round_number = 1
    g.state.collapse_bar = 0
    g.state.active_crises = []
    return g


def test_finale_run_advances_escape_track():
    g = _make_finale_game(4)
    p = g.state.players[0]
    assert p.escape_track == 0
    g.submit_action(PlayerAction(
        player_id=p.id,
        action_type=ActionType.RUN,
    ))
    g.resolve_round()
    assert p.escape_track == 1


def test_finale_run_caps_escape_track_at_3():
    g = _make_finale_game(4)
    p = g.state.players[0]
    p.escape_track = 2
    g.submit_action(PlayerAction(
        player_id=p.id,
        action_type=ActionType.RUN,
    ))
    g.resolve_round()
    assert p.escape_track == 3  # capped


def test_finale_carry_with_two_carriers_advances_downed():
    g = _make_finale_game(4)
    downed = g.state.players[0]
    downed.is_down = True
    assert downed.escape_track == 0
    # Two other players carry
    g.submit_action(PlayerAction(
        player_id=g.state.players[1].id,
        action_type=ActionType.CARRY,
        target_player_id=downed.id,
    ))
    g.submit_action(PlayerAction(
        player_id=g.state.players[2].id,
        action_type=ActionType.CARRY,
        target_player_id=downed.id,
    ))
    g.resolve_round()
    assert downed.escape_track == 1


def test_finale_carry_with_one_carrier_does_not_advance():
    g = _make_finale_game(4)
    downed = g.state.players[0]
    downed.is_down = True
    # Only 1 carrier (needs 2)
    g.submit_action(PlayerAction(
        player_id=g.state.players[1].id,
        action_type=ActionType.CARRY,
        target_player_id=downed.id,
    ))
    g.resolve_round()
    assert downed.escape_track == 0  # did not advance


def test_finale_carry_caps_escape_track_at_3():
    g = _make_finale_game(4)
    downed = g.state.players[0]
    downed.is_down = True
    downed.escape_track = 2
    g.submit_action(PlayerAction(
        player_id=g.state.players[1].id,
        action_type=ActionType.CARRY,
        target_player_id=downed.id,
    ))
    g.submit_action(PlayerAction(
        player_id=g.state.players[2].id,
        action_type=ActionType.CARRY,
        target_player_id=downed.id,
    ))
    g.resolve_round()
    assert downed.escape_track == 3  # capped


def test_finale_hold_reduces_collapse_bar():
    g = _make_finale_game(4)
    g.state.collapse_bar = 50
    g.submit_action(PlayerAction(
        player_id=g.state.players[0].id,
        action_type=ActionType.HOLD,
    ))
    g.resolve_round()
    # 50 + 34 (base) - 15 (one hold) = 69
    assert g.state.collapse_bar == 69


def test_finale_collapse_reaching_100_triggers_end():
    g = _make_finale_game(4)
    g.state.collapse_bar = 68
    # No HOLDs → 68 + 34 = 102 >= 100 → end_finale
    for p in g.state.players:
        g.submit_action(PlayerAction(
            player_id=p.id,
            action_type=ActionType.RUN,
        ))
    g.resolve_round()
    assert g.state.phase == Phase.RESULTS
    assert g.state.victory is False  # not everyone escaped
    assert len(g.state.crew_lost) > 0


def test_finale_collapse_reaching_100_with_one_hold_does_not_trigger():
    g = _make_finale_game(4)
    g.state.collapse_bar = 66
    # One HOLD → 66 + 34 - 15 = 85 < 100 → continues
    g.submit_action(PlayerAction(
        player_id=g.state.players[0].id,
        action_type=ActionType.HOLD,
    ))
    g.resolve_round()
    assert g.state.phase == Phase.FINALE  # not ended


def test_finale_all_crew_escape_triggers_win():
    g = _make_finale_game(4)
    # Set all players to escape_track 2, RUN to reach 3
    for p in g.state.players:
        p.escape_track = 2
    for p in g.state.players:
        g.submit_action(PlayerAction(
            player_id=p.id,
            action_type=ActionType.RUN,
        ))
    g.resolve_round()
    assert g.state.phase == Phase.RESULTS
    assert g.state.victory is True
    assert len(g.state.crew_lost) == 0
    assert len(g.state.crew_survived) == 4


def test_finale_partial_escape():
    g = _make_finale_game(4)
    # Two escape, two don't
    g.state.players[0].escape_track = 2
    g.state.players[1].escape_track = 2
    g.state.players[2].escape_track = 0
    g.state.players[3].escape_track = 0
    # Round 1: first two RUN to safety, others HOLD (collapse 0+34-30=4)
    g.submit_action(PlayerAction(
        player_id=g.state.players[0].id,
        action_type=ActionType.RUN,
    ))
    g.submit_action(PlayerAction(
        player_id=g.state.players[1].id,
        action_type=ActionType.RUN,
    ))
    g.submit_action(PlayerAction(
        player_id=g.state.players[2].id,
        action_type=ActionType.HOLD,
    ))
    g.submit_action(PlayerAction(
        player_id=g.state.players[3].id,
        action_type=ActionType.HOLD,
    ))
    g.resolve_round()
    assert g.state.phase == Phase.FINALE  # not over yet
    assert g.state.round_number == 2
    # Round 2: survivors already at 3 (capped), non-escapers HOLD
    # collapse = 4 + 34 - 30 = 8
    g.submit_action(PlayerAction(
        player_id=g.state.players[0].id,
        action_type=ActionType.RUN,
    ))
    g.submit_action(PlayerAction(
        player_id=g.state.players[1].id,
        action_type=ActionType.RUN,
    ))
    g.submit_action(PlayerAction(
        player_id=g.state.players[2].id,
        action_type=ActionType.HOLD,
    ))
    g.submit_action(PlayerAction(
        player_id=g.state.players[3].id,
        action_type=ActionType.HOLD,
    ))
    g.resolve_round()
    assert g.state.phase == Phase.FINALE  # round 3
    assert g.state.round_number == 3
    # Round 3: same → round_number becomes 4 > 3 → end_finale (partial)
    g.submit_action(PlayerAction(
        player_id=g.state.players[0].id,
        action_type=ActionType.RUN,
    ))
    g.submit_action(PlayerAction(
        player_id=g.state.players[1].id,
        action_type=ActionType.RUN,
    ))
    g.submit_action(PlayerAction(
        player_id=g.state.players[2].id,
        action_type=ActionType.HOLD,
    ))
    g.submit_action(PlayerAction(
        player_id=g.state.players[3].id,
        action_type=ActionType.HOLD,
    ))
    g.resolve_round()
    assert g.state.phase == Phase.RESULTS
    assert g.state.victory is False
    assert g.state.partial is True
    assert len(g.state.crew_survived) == 2
    assert len(g.state.crew_lost) == 2


def test_finale_round_past_3_triggers_end():
    g = _make_finale_game(4)
    g.state.round_number = 3
    # Nobody escapes (all HOLD to avoid collapse)
    for p in g.state.players:
        g.submit_action(PlayerAction(
            player_id=p.id,
            action_type=ActionType.HOLD,
        ))
    g.resolve_round()
    # round_number becomes 4 > 3 → end_finale
    assert g.state.phase == Phase.RESULTS
    assert g.state.victory is False
    assert len(g.state.crew_lost) == 4