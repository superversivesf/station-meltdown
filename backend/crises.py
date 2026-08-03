import random
from models import Crisis, SystemName


def _c(id, name, desc, system, drain, crew, tier, variants=None):
    return Crisis(
        id=id,
        name=name,
        description=desc,
        system=system,
        drain_rate=drain,
        crew_required=crew,
        tier=tier,
        weight=10,
        name_variants=variants or [],
        desc_variants=[],
    )


CRISIS_POOL: list[Crisis] = [
    # --- Tier 1 (rounds 1-3, drain 2-4, crew 1-2) — 15 crises ---
    _c("coolant_leak", "Coolant Leak", "Coolant spraying from reactor coupling",
       SystemName.REACTOR, 3, 2, 1, ["Coolant Line Rupture", "Primary Coolant Failure"]),
    _c("o2_scrubber_stall", "O2 Scrubber Stall", "CO2 scrubbers offline in section 3",
       SystemName.LIFE_SUPPORT, 2, 1, 1, ["Scrubber Malfunction", "Air Recycler Fault"]),
    _c("med_bot_error", "Med Bot Error", "Medical bot dispensing wrong dosage",
       SystemName.MED_BAY, 2, 1, 1, ["Med Bot Glitch", "Pharmacy System Fault"]),
    _c("hull_microfracture", "Hull Microfracture", "Hairline crack in outer hull",
       SystemName.HULL, 3, 1, 1, ["Hull Stress Point", "Microfracture Detected"]),
    _c("comms_static", "Comms Static", "Rescue signal drowning in static",
       SystemName.COMMS, 2, 1, 1, ["Signal Degradation", "Comms Interference"]),
    _c("shield_flicker", "Shield Flicker", "Shields flickering on port side",
       SystemName.SHIELDS, 2, 1, 1, ["Shield Fluctuation", "Port Shield Instability"]),
    _c("reactor_vibration", "Reactor Vibration", "Unusual vibration from reactor core",
       SystemName.REACTOR, 4, 2, 1, ["Core Vibration", "Reactor Tremor"]),
    _c("airlock_seal", "Airlock Seal Fault", "Airlock not sealing properly",
       SystemName.HULL, 3, 2, 1, ["Airlock Gap", "Seal Failure"]),
    _c("filter_clog", "Filter Clog", "Particulate filter clogging air flow",
       SystemName.LIFE_SUPPORT, 2, 1, 1, ["Clogged Filter", "Airflow Blockage"]),
    _c("antenna_drift", "Antenna Drift", "Comms antenna misaligned by 3 degrees",
       SystemName.COMMS, 2, 1, 1, ["Antenna Misalignment", "Signal Drift"]),
    _c("shield_coolant", "Shield Coolant Low", "Shield coolant below 30%",
       SystemName.SHIELDS, 3, 1, 1, ["Coolant Depletion", "Shield Fluid Low"]),
    _c("med_supply_low", "Med Supply Low", "Medical supplies running low",
       SystemName.MED_BAY, 2, 1, 1, ["Supply Depletion", "Medkit Shortage"]),
    _c("reactor_heat", "Reactor Heat Spike", "Reactor running 15% above normal",
       SystemName.REACTOR, 3, 2, 1, ["Thermal Spike", "Heat Surge"]),
    _c("hull_corrosion", "Hull Corrosion", "Corrosion spreading on outer plating",
       SystemName.HULL, 2, 1, 1, ["Plating Rust", "Structural Corrosion"]),
    _c("comms_relay", "Comms Relay Fault", "Relay switch stuck in loop",
       SystemName.COMMS, 2, 1, 1, ["Relay Loop", "Switch Stuck"]),

    # --- Tier 2 (rounds 4-7, drain 3-6, crew 2) — 15 crises ---
    _c("reactor_overheat", "Reactor Overheat", "Core temperature critical",
       SystemName.REACTOR, 5, 2, 2, ["Critical Overheat", "Core Thermal Runaway"]),
    _c("life_support_fail", "Life Support Failure", "O2 generation at 40%",
       SystemName.LIFE_SUPPORT, 4, 2, 2, ["O2 System Failure", "Air Generator Down"]),
    _c("med_quarantine", "Med Bay Quarantine", "Biohazard in med bay",
       SystemName.MED_BAY, 3, 2, 2, ["Biohazard Lockdown", "Contamination Alert"]),
    _c("hull_breach", "Hull Breach", "Section 7 breached to vacuum",
       SystemName.HULL, 6, 2, 2, ["Vacuum Breach", "Section 7 Open"]),
    _c("comms_blackout", "Comms Blackout", "All external comms lost",
       SystemName.COMMS, 4, 2, 2, ["Total Signal Loss", "Comms Dark"]),
    _c("shield_collapse", "Shield Collapse", "Aft shields down to 20%",
       SystemName.SHIELDS, 5, 2, 2, ["Aft Shield Failure", "Shield Generator Down"]),
    _c("reactor_leak", "Reactor Coolant Leak", "Primary coolant leaking fast",
       SystemName.REACTOR, 6, 2, 2, ["Coolant Hemorrhage", "Primary Leak"]),
    _c("o2_contamination", "O2 Contamination", "Toxic gas in air supply",
       SystemName.LIFE_SUPPORT, 5, 2, 2, ["Toxic Air", "Air Poisoning"]),
    _c("med_power_loss", "Med Bay Power Loss", "Med bay on backup power",
       SystemName.MED_BAY, 3, 2, 2, ["Med Bay Dark", "Backup Power Only"]),
    _c("hull_structural", "Hull Structural Failure", "Frame bending in section 4",
       SystemName.HULL, 5, 2, 2, ["Frame Warping", "Structural Failure"]),
    _c("comms_hardware", "Comms Hardware Burnout", "Transmitter fried",
       SystemName.COMMS, 4, 2, 2, ["Transmitter Burnout", "Hardware Failure"]),
    _c("shield_overload", "Shield Overload", "Generators drawing too much power",
       SystemName.SHIELDS, 4, 2, 2, ["Generator Overload", "Power Surge"]),
    _c("reactor_control", "Reactor Control Rod Jam", "Control rod stuck",
       SystemName.REACTOR, 5, 2, 2, ["Rod Jam", "Control Failure"]),
    _c("life_filter_fail", "Life Support Filter Failure", "Main filter collapsed",
       SystemName.LIFE_SUPPORT, 4, 2, 2, ["Filter Collapse", "Filtration Down"]),
    _c("hull_window_crack", "Hull Window Crack", "Observation window cracking",
       SystemName.HULL, 4, 2, 2, ["Window Fracture", "Glass Failure"]),

    # --- Tier 3 (rounds 8-10, drain 5-10, crew 2-3) — 10 crises ---
    _c("reactor_meltdown_risk", "Reactor Meltdown Risk", "Core approaching meltdown",
       SystemName.REACTOR, 8, 3, 3, ["Meltdown Imminent", "Critical Core"]),
    _c("life_total_fail", "Life Support Total Failure", "O2 at 10% and falling",
       SystemName.LIFE_SUPPORT, 7, 3, 3, ["O2 Critical", "Air Almost Gone"]),
    _c("med_explosion", "Med Bay Explosion", "Equipment explosion in med bay",
       SystemName.MED_BAY, 5, 2, 3, ["Med Bay Wrecked", "Pharmacy Destroyed"]),
    _c("hull_catastrophic", "Catastrophic Hull Breach", "Multiple sections open",
       SystemName.HULL, 8, 3, 3, ["Multi-Section Breach", "Hull Gone"]),
    _c("comms_destroyed", "Comms Array Destroyed", "Antenna array shattered",
       SystemName.COMMS, 5, 2, 3, ["Array Wreckage", "No Signal Possible"]),
    _c("shield_offline", "Shields Offline", "All shield generators dead",
       SystemName.SHIELDS, 7, 3, 3, ["Shields Down", "Unguarded"]),
    _c("reactor_coolant_loss", "Total Coolant Loss", "No coolant remaining",
       SystemName.REACTOR, 10, 3, 3, ["Coolant Empty", "Dry Core"]),
    _c("life_toxic_flood", "Toxic Atmosphere Flood", "Station filling with toxins",
       SystemName.LIFE_SUPPORT, 6, 3, 3, ["Toxic Flood", "Poison Air"]),
    _c("hull_frame_collapse", "Hull Frame Collapse", "Station frame buckling",
       SystemName.HULL, 7, 3, 3, ["Frame Buckling", "Structural Collapse"]),
    _c("shield_inverter_fire", "Shield Inverter Fire", "Inverter burning out",
       SystemName.SHIELDS, 6, 2, 3, ["Inverter Blaze", "Fire in Generators"]),
]


def _with_variant(crisis: Crisis) -> Crisis:
    chosen = crisis.model_copy()
    if chosen.name_variants:
        all_names = [chosen.name] + chosen.name_variants
        chosen.name = random.choice(all_names)
    return chosen


def get_crisis_count(round_number: int) -> int:
    if round_number <= 3:
        return 1
    elif round_number <= 7:
        return 2
    else:
        return 3


def spawn_crises(round_number: int) -> list[Crisis]:
    count = get_crisis_count(round_number)
    # Filter pool by valid tier for this round
    if round_number <= 3:
        valid_tiers = {1}
    elif round_number <= 7:
        valid_tiers = {1, 2}
    else:
        valid_tiers = {1, 2, 3}
    pool = [c for c in CRISIS_POOL if c.tier in valid_tiers]

    selected: list[Crisis] = []
    used_systems: set[SystemName] = set()
    attempts = 0
    max_attempts = 100

    while len(selected) < count and attempts < max_attempts:
        attempts += 1
        # Weighted random selection
        weights = [c.weight for c in pool]
        choice = random.choices(pool, weights=weights, k=1)[0]
        if choice.system in used_systems:
            continue
        used_systems.add(choice.system)
        chosen = _with_variant(choice)
        selected.append(chosen)
        pool = [c for c in pool if c.system not in used_systems]

    # Ensure at least one crisis requires crew >= 2
    if not any(c.crew_required >= 2 for c in selected):
        # Find a multi-crew crisis on an unused system
        multi_pool = [c for c in CRISIS_POOL
                      if c.tier in valid_tiers
                      and c.crew_required >= 2
                      and c.system not in used_systems]
        if multi_pool:
            replacement = random.choice(multi_pool)
            chosen = _with_variant(replacement)
            # Replace the last single-crew crisis
            selected[-1] = chosen

    return selected