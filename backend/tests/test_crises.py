import pytest
from crises import CRISIS_POOL, spawn_crises, get_crisis_count
from models import SystemName


def test_pool_has_40_crises():
    assert len(CRISIS_POOL) == 40


def test_pool_has_tier_distribution():
    tier1 = [c for c in CRISIS_POOL if c.tier == 1]
    tier2 = [c for c in CRISIS_POOL if c.tier == 2]
    tier3 = [c for c in CRISIS_POOL if c.tier == 3]
    # Assert the pool has all three tiers and tier-1 is the largest
    assert len(tier1) > 0
    assert len(tier2) > 0
    assert len(tier3) > 0
    assert len(tier1) >= len(tier2) >= len(tier3)


def test_get_crisis_count():
    assert get_crisis_count(1) == 1
    assert get_crisis_count(3) == 1
    assert get_crisis_count(4) == 2
    assert get_crisis_count(7) == 2
    assert get_crisis_count(8) == 3
    assert get_crisis_count(10) == 3


def test_spawn_returns_correct_count():
    # Round 1: 1 crisis
    crises = spawn_crises(1)
    assert len(crises) == 1
    # Round 5: 2 crises
    crises = spawn_crises(5)
    assert len(crises) == 2
    # Round 9: 3 crises
    crises = spawn_crises(9)
    assert len(crises) == 3


def test_spawn_respects_tier_gating():
    # Round 1 should only spawn tier 1 crises
    for _ in range(20):
        crises = spawn_crises(1)
        for c in crises:
            assert c.tier == 1
    # Round 5 can spawn tier 1 or 2
    for _ in range(20):
        crises = spawn_crises(5)
        for c in crises:
            assert c.tier in (1, 2)
    # Round 9 can spawn any tier
    for _ in range(20):
        crises = spawn_crises(9)
        for c in crises:
            assert c.tier in (1, 2, 3)


def test_spawn_no_duplicate_systems():
    for _ in range(50):
        crises = spawn_crises(9)
        systems = [c.system for c in crises]
        assert len(systems) == len(set(systems)), f"Duplicate systems: {systems}"


def test_spawn_at_least_one_multi_crew():
    for _ in range(50):
        crises = spawn_crises(5)
        has_multi = any(c.crew_required >= 2 for c in crises)
        assert has_multi, "Every spawn must include at least one crew_required>=2 crisis"


def test_spawn_uses_variants():
    # Run spawn many times, collect names — should see variety
    names_seen = set()
    for _ in range(100):
        crises = spawn_crises(5)
        for c in crises:
            names_seen.add(c.name)
    # ~30 base names in tier-{1,2} pool; variants add ~50 more distinct names.
    # Threshold >35 distinguishes "variants work" (~80 distinct) from
    # "variants don't work" (~30 distinct). Fails if variant logic removed.
    assert len(names_seen) > 35