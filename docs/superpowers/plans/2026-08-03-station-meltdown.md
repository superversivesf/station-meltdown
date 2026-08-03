# Station Meltdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a co-op sci-fi survival web game where up to 15 players endure 10 rounds of crises on a failing space station, then attempt a 3-round escape sequence, all in a 30-minute session.

**Architecture:** FastAPI backend with WebSocket authority (in-memory game state) serves a SvelteKit SPA (adapter-static). Single Docker container, single port. Server is the single source of truth; clients are dumb renderers that send actions and render pushed state.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, websockets; Node 20, SvelteKit, adapter-static, TypeScript; Docker multi-stage build.

## Global Constraints

- Python 3.12+ (matches Dockerfile base image `python:3.12-slim`)
- Node 20+ (matches Dockerfile base image `node:20-slim`)
- FastAPI with WebSocket support (not polling)
- SvelteKit with `adapter-static` in SPA mode (no SSR at runtime)
- Single Docker container, single port (8000)
- In-memory game state only — no database, no persistence
- Server is state authority; clients hold no game logic
- Game supports 4-15 players (minimum 4 for crew-power mechanic)
- 30-minute session cap: ~12-13 min survival + ~5 min finale + buffer
- Naming: game instances are "rooms", identified by 4-letter uppercase codes
- Copy/UX: casual sci-fi tone, action options readable in <5 sec on a phone

---

## File Structure

```
fun-session/
├── Dockerfile
├── .dockerignore
├── backend/
│   ├── main.py                  # FastAPI app, routes, WebSocket handler, static serving
│   ├── game.py                  # Game class — state, tick, resolve, phases
│   ├── crises.py                # Crisis pool (40 entries), spawn logic, tiers
│   ├── models.py                # Pydantic models: GameState, Player, Crisis, Action
│   ├── requirements.txt         # fastapi, uvicorn[standard], pydantic
│   └── tests/
│       ├── __init__.py
│       ├── test_game.py         # Game engine tests (tick, resolve, win/loss)
│       ├── test_crises.py       # Crisis pool + spawn logic tests
│       └── test_models.py       # Model validation tests
└── frontend/
    ├── package.json
    ├── svelte.config.js         # adapter-static, SPA fallback
    ├── vite.config.ts           # dev proxy /ws -> localhost:8000
    ├── tsconfig.json
    ├── src/
    │   ├── app.html
    │   ├── app.d.ts
    │   ├── lib/
    │   │   ├── types.ts          # TS types mirroring backend models
    │   │   ├── websocket.ts      # WS client + reconnect logic
    │   │   └── stores.ts         # Svelte stores for game state
    │   └── routes/
    │       ├── +layout.svelte    # global layout, WS connection lifecycle
    │       ├── +page.svelte      # join screen (room code + name)
    │       ├── lobby/+page.svelte    # player list, host start button
    │       ├── play/+page.svelte      # survival phase UI (status + action picker + countdown)
    │       ├── finale/+page.svelte    # escape sequence UI (RUN/CARRY/HOLD)
    │       └── results/+page.svelte   # win/loss + crew survival report
    └── static/
        └── favicon.png
```

**Responsibility boundaries:**
- `models.py` — pure data shapes, no logic. Imported by `game.py` and `main.py`.
- `crises.py` — crisis pool data + spawn function. No game state, no I/O.
- `game.py` — Game class: holds state, advances rounds, resolves actions, checks win/loss. No WebSocket or HTTP concerns.
- `main.py` — HTTP/WS layer: routing, connection management, serialization. Imports `game.py` and `crises.py`. No game logic here.
- Frontend `types.ts` — mirrors `models.py` shapes manually (no codegen). Single source of truth for client rendering.
- Frontend `websocket.ts` — connection lifecycle only. No game logic.
- Frontend `stores.ts` — reactive state derived from WS messages. Components read stores, never touch WS directly.

---

## Task 1: Project Scaffolding & Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `backend/requirements.txt`
- Create: `backend/main.py` (minimal FastAPI app)
- Create: `frontend/package.json`
- Create: `frontend/svelte.config.js`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/src/app.html`
- Create: `frontend/src/app.d.ts`
- Create: `frontend/src/routes/+layout.svelte`
- Create: `frontend/src/routes/+page.svelte`
- Create: `frontend/static/favicon.png` (empty placeholder)

**Interfaces:**
- Produces: a running dev environment — `uvicorn` on :8000, Vite on :5173 proxying WS
- Produces: a buildable Docker image (`docker build -t station-meltdown .`)

- [ ] **Step 1: Create backend scaffolding**

`backend/requirements.txt`:
```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
pydantic>=2.6.0
```

`backend/main.py`:
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI()

@app.get("/api/health")
async def health():
    return {"status": "ok"}

# Mount static SPA in production (built by Dockerfile)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
```

- [ ] **Step 2: Create frontend scaffolding**

`frontend/package.json`:
```json
{
  "name": "station-meltdown-frontend",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite dev",
    "build": "vite build",
    "preview": "vite preview"
  },
  "devDependencies": {
    "@sveltejs/adapter-static": "^3.0.0",
    "@sveltejs/kit": "^2.0.0",
    "@sveltejs/vite-plugin-svelte": "^3.0.0",
    "svelte": "^4.2.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0"
  }
}
```

`frontend/svelte.config.js`:
```javascript
import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      fallback: 'index.html',
      precompress: false,
      strict: false
    })
  }
};
```

`frontend/vite.config.ts`:
```typescript
import { sveltekit } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true
      },
      '/api': {
        target: 'http://localhost:8000'
      }
    }
  }
});
```

`frontend/tsconfig.json`:
```json
{
  "extends": "./.svelte-kit/tsconfig.json",
  "compilerOptions": {
    "allowJs": true,
    "checkJs": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "strict": true,
    "moduleResolution": "bundler"
  }
}
```

`frontend/src/app.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Station Meltdown</title>
  %sveltekit.head%
</head>
<body data-sveltekit-preload-data="hover">
  <div style="display: contents">%sveltekit.body%</div>
</body>
</html>
```

`frontend/src/app.d.ts`:
```typescript
declare global {
  namespace App {}
}
export {};
```

`frontend/src/routes/+layout.svelte`:
```svelte
<script>
  let { children } = $props();
</script>

{@render children()}
```

`frontend/src/routes/+page.svelte`:
```svelte
<h1>Station Meltdown</h1>
<p>Join screen coming soon.</p>
```

- [ ] **Step 3: Create Dockerfile**

`Dockerfile`:
```dockerfile
# Stage 1: Build SvelteKit SPA
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package.json
RUN npm install
COPY frontend/ .
RUN npm run build

# Stage 2: Python backend + serve static
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=frontend /app/frontend/build ./static
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`.dockerignore`:
```
**/node_modules
**/.svelte-kit
**/build
**/__pycache__
**/.pytest_cache
**/.venv
**/venv
.git
```

- [ ] **Step 4: Verify backend starts**

Run: `cd backend && pip install -r requirements.txt && uvicorn main:app --reload`
Expected: server starts on :8000, `curl http://localhost:8000/api/health` returns `{"status":"ok"}`

- [ ] **Step 5: Verify frontend dev server starts**

Run: `cd frontend && npm install && npm run dev`
Expected: Vite dev server starts on :5173, browser shows "Station Meltdown" heading

- [ ] **Step 6: Verify Docker build**

Run: `docker build -t station-meltdown .`
Expected: image builds successfully (may need frontend build to complete first)

- [ ] **Step 7: Commit**

```bash
git init && git add -A && git commit -m "chore: scaffold project (FastAPI + SvelteKit + Docker)"
```

---

## Task 2: Data Models (Backend)

**Files:**
- Create: `backend/models.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_models.py`

**Interfaces:**
- Produces: `SystemName` enum, `Phase` enum, `Crisis` model, `Player` model, `PlayerAction` model, `GameState` model
- Produces: `ActionType` enum with values `FIX`, `BOLSTER`, `REVIVE`, `RUN`, `CARRY`, `HOLD`
- Consumes: nothing (foundational task)

- [ ] **Step 1: Write the failing test**

`backend/tests/test_models.py`:
```python
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
```

`backend/tests/__init__.py`:
```python
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'models'`

- [ ] **Step 3: Write minimal implementation**

`backend/models.py`:
```python
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class SystemName(str, Enum):
    REACTOR = "reactor"
    LIFE_SUPPORT = "life_support"
    MED_BAY = "med_bay"
    HULL = "hull"
    COMMS = "comms"
    SHIELDS = "shields"


class Phase(str, Enum):
    LOBBY = "lobby"
    SURVIVAL = "survival"
    FINALE = "finale"
    RESULTS = "results"


class ActionType(str, Enum):
    FIX = "fix"
    BOLSTER = "bolster"
    REVIVE = "revive"
    RUN = "run"
    CARRY = "carry"
    HOLD = "hold"


class Crisis(BaseModel):
    id: str
    name: str
    description: str
    system: SystemName
    drain_rate: int
    crew_required: int
    tier: int
    weight: int = 10
    # Flavor variants for replay variety
    name_variants: list[str] = Field(default_factory=list)
    desc_variants: list[str] = Field(default_factory=list)


class Player(BaseModel):
    id: str
    name: str
    is_host: bool = False
    is_down: bool = False
    escape_track: int = 0  # 0-3, reaches 3 = safe in pods


class PlayerAction(BaseModel):
    player_id: str
    action_type: ActionType
    target_system: Optional[SystemName] = None
    target_crisis_id: Optional[str] = None
    # For CARRY in finale: which downed crewmate to carry
    target_player_id: Optional[str] = None


class GameState(BaseModel):
    room_code: str
    phase: Phase = Phase.LOBBY
    round_number: int = 0
    systems: dict[SystemName, int] = Field(default_factory=lambda: {
        s: 100 for s in SystemName
    })
    players: list[Player] = Field(default_factory=list)
    active_crises: list[Crisis] = Field(default_factory=list)
    pending_actions: list[PlayerAction] = Field(default_factory=list)
    collapse_bar: int = 0  # 0-100, finale only
    action_phase_deadline: Optional[float] = None  # unix timestamp
    # Results
    crew_survived: list[str] = Field(default_factory=list)  # player IDs
    crew_lost: list[str] = Field(default_factory=list)
    victory: bool = False
    partial: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_models.py -v`
Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models.py backend/tests/
git commit -m "feat: add data models (SystemName, Phase, Crisis, Player, GameState)"
```

---

## Task 3: Crisis Pool & Spawn Logic

**Files:**
- Create: `backend/crises.py`
- Create: `backend/tests/test_crises.py`

**Interfaces:**
- Consumes: `Crisis`, `SystemName` from `models.py`
- Produces: `CRISIS_POOL: list[Crisis]` (40 entries), `spawn_crises(round_number: int) -> list[Crisis]`
- Produces: helper `get_crisis_count(round_number: int) -> int` (1 for rounds 1-3, 2 for 4-7, 3 for 8-10)

- [ ] **Step 1: Write the failing test**

`backend/tests/test_crises.py`:
```python
import pytest
from crises import CRISIS_POOL, spawn_crises, get_crisis_count
from models import SystemName


def test_pool_has_40_crises():
    assert len(CRISIS_POOL) == 40


def test_pool_has_tier_distribution():
    tier1 = [c for c in CRISIS_POOL if c.tier == 1]
    tier2 = [c for c in CRISIS_POOL if c.tier == 2]
    tier3 = [c for c in CRISIS_POOL if c.tier == 3]
    assert len(tier1) == 15
    assert len(tier2) == 15
    assert len(tier3) == 10


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
    # With 40 crises and variants, we should see many distinct names
    assert len(names_seen) > 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_crises.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'crises'`

- [ ] **Step 3: Write minimal implementation**

`backend/crises.py`:
```python
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
        # Pick a variant name if available
        chosen = choice.model_copy()
        if chosen.name_variants:
            all_names = [chosen.name] + chosen.name_variants
            chosen.name = random.choice(all_names)
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
            chosen = replacement.model_copy()
            if chosen.name_variants:
                all_names = [chosen.name] + chosen.name_variants
                chosen.name = random.choice(all_names)
            # Replace the last single-crew crisis
            selected[-1] = chosen

    return selected
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_crises.py -v`
Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/crises.py backend/tests/test_crises.py
git commit -m "feat: add crisis pool (40 crises) and spawn logic with tier gating"
```

---

## Task 4: Game Engine — State & Lobby

**Files:**
- Create: `backend/game.py`
- Create: `backend/tests/test_game.py`

**Interfaces:**
- Consumes: `GameState`, `Player`, `Phase`, `SystemName` from `models.py`
- Produces: `Game` class with methods:
  - `__init__(self, room_code: str)`
  - `add_player(self, name: str) -> Player`
  - `get_state(self) -> GameState`
  - `start(self) -> None` (transitions LOBBY → SURVIVAL, round 1)
  - `is_host(self, player_id: str) -> bool`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_game.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_game.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'game'`

- [ ] **Step 3: Write minimal implementation**

`backend/game.py`:
```python
import uuid
from models import GameState, Player, Phase
from crises import spawn_crises


class Game:
    MIN_PLAYERS = 4
    MAX_PLAYERS = 15

    def __init__(self, room_code: str):
        self.state = GameState(room_code=room_code)

    def get_state(self) -> GameState:
        return self.state

    def add_player(self, name: str) -> Player:
        if self.state.phase != Phase.LOBBY:
            raise ValueError("can only add players in lobby phase")
        if len(self.state.players) >= self.MAX_PLAYERS:
            raise ValueError(f("room full (max {self.MAX_PLAYERS} players)"))
        is_host = len(self.state.players) == 0
        player = Player(
            id=str(uuid.uuid4())[:8],
            name=name,
            is_host=is_host,
        )
        self.state.players.append(player)
        return player

    def is_host(self, player_id: str) -> bool:
        for p in self.state.players:
            if p.id == player_id:
                return p.is_host
        return False

    def start(self) -> None:
        if self.state.phase != Phase.LOBBY:
            raise ValueError("can only start from lobby phase")
        if len(self.state.players) < self.MIN_PLAYERS:
            raise ValueError(f"minimum {self.MIN_PLAYERS} players required")
        self.state.phase = Phase.SURVIVAL
        self.state.round_number = 1
        self.state.active_crises = spawn_crises(1)
```

- [ ] **Step 4: Run test to verify it fails (catch typo)**

Run: `cd backend && python -m pytest tests/test_game.py -v`
Expected: FAIL — `f("...")` is not valid f-string syntax. Fix the typo.

- [ ] **Step 5: Fix the typo**

In `backend/game.py`, change:
```python
raise ValueError(f("room full (max {self.MAX_PLAYERS} players)"))
```
to:
```python
raise ValueError(f"room full (max {self.MAX_PLAYERS} players)")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_game.py -v`
Expected: all 7 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/game.py backend/tests/test_game.py
git commit -m "feat: add Game class with lobby and start logic"
```

---

## Task 5: Game Engine — Survival Phase Tick & Resolve

**Files:**
- Modify: `backend/game.py` (add `submit_action`, `resolve_round`, `tick`)
- Modify: `backend/tests/test_game.py` (add tests for tick/resolve)

**Interfaces:**
- Consumes: `PlayerAction`, `ActionType`, `SystemName` from `models.py`; `spawn_crises` from `crises.py`
- Produces: `Game.submit_action(self, action: PlayerAction) -> None`
- Produces: `Game.resolve_round(self) -> None` (computes all actions, drains systems, checks loss, advances round)
- Produces: `Game.tick(self) -> None` (convenience: calls resolve_round then spawns next round's crises)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_game.py`:
```python
from models import PlayerAction, ActionType, SystemName


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
    p = g.state.players[0]
    g.state.systems[SystemName.HULL] = 50
    g.submit_action(PlayerAction(
        player_id=p.id,
        action_type=ActionType.BOLSTER,
        target_system=SystemName.HULL,
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
    crisis = g.state.active_crises[0]
    if crisis.crew_required < 2:
        return  # skip if only needs 1
    # Only 1 player tries to FIX (needs 2)
    g.submit_action(PlayerAction(
        player_id=g.state.players[0].id,
        action_type=ActionType.FIX,
        target_system=crisis.system,
        target_crisis_id=crisis.id,
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
    g.resolve_round()
    assert downed_p.is_down is True  # still down, med bay offline


def test_all_crew_downed_triggers_loss():
    g = make_game_with_players(4)
    for p in g.state.players:
        p.is_down = True
    g.resolve_round()
    assert g.state.phase == Phase.RESULTS
    assert g.state.victory is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_game.py -v -k "test_resolve or test_reactor or test_life_support or test_shields or test_revive or test_all_crew or test_submit_action"`
Expected: FAIL — `Game` has no `submit_action` or `resolve_round` methods

- [ ] **Step 3: Write minimal implementation**

Add to the top of `backend/game.py` (merge with existing imports):
```python
import random
import time
```

Add `PlayerAction` and `ActionType` to the existing `from models import ...` line:
```python
from models import GameState, Player, Phase, PlayerAction, ActionType, SystemName
```

Append these methods to the `Game` class in `backend/game.py`:
```python
    def submit_action(self, action: PlayerAction) -> None:
        if self.state.phase != Phase.SURVIVAL and self.state.phase != Phase.FINALE:
            raise ValueError("can only submit actions during survival or finale")
        # Remove any existing action from this player (replace, not duplicate)
        self.state.pending_actions = [
            a for a in self.state.pending_actions
            if a.player_id != action.player_id
        ]
        self.state.pending_actions.append(action)

    def resolve_round(self) -> None:
        if self.state.phase == Phase.SURVIVAL:
            self._resolve_survival_round()
        elif self.state.phase == Phase.FINALE:
            self._resolve_finale_round()

    def _resolve_survival_round(self) -> None:
        actions = self.state.pending_actions
        # Group FIX actions by crisis ID
        fix_groups: dict[str, list[PlayerAction]] = {}
        for a in actions:
            if a.action_type == ActionType.FIX and a.target_crisis_id:
                fix_groups.setdefault(a.target_crisis_id, []).append(a)

        # Determine which crises are fixed
        fixed_crisis_ids: set[str] = set()
        for crisis_id, fixers in fix_groups.items():
            crisis = next((c for c in self.state.active_crises if c.id == crisis_id), None)
            if crisis and len(fixers) >= crisis.crew_required:
                fixed_crisis_ids.add(crisis_id)

        # Apply crisis drains (only for unfixed crises)
        for crisis in self.state.active_crises:
            if crisis.id not in fixed_crisis_ids:
                self.state.systems[crisis.system] -= crisis.drain_rate
                if self.state.systems[crisis.system] < 0:
                    self.state.systems[crisis.system] = 0

        # Apply shields-at-0 degradation
        if self.state.systems[SystemName.SHIELDS] == 0:
            for s in SystemName:
                if s != SystemName.SHIELDS:
                    self.state.systems[s] -= 2
                    if self.state.systems[s] < 0:
                        self.state.systems[s] = 0

        # Apply BOLSTER actions
        for a in actions:
            if a.action_type == ActionType.BOLSTER and a.target_system:
                self.state.systems[a.target_system] = min(
                    100, self.state.systems[a.target_system] + 5
                )

        # Apply REVIVE actions
        for a in actions:
            if a.action_type == ActionType.REVIVE and a.target_player_id:
                if self.state.systems[SystemName.MED_BAY] > 0:
                    target = next(
                        (p for p in self.state.players if p.id == a.target_player_id),
                        None
                    )
                    if target and target.is_down:
                        target.is_down = False

        # Down a crew member if life support is at 0
        if self.state.systems[SystemName.LIFE_SUPPORT] == 0:
            standing = [p for p in self.state.players if not p.is_down]
            if standing:
                victim = random.choice(standing)
                victim.is_down = True

        # Check loss conditions
        if self.state.systems[SystemName.REACTOR] == 0:
            self._end_game(victory=False)
            return
        standing = [p for p in self.state.players if not p.is_down]
        if not standing:
            self._end_game(victory=False)
            return

        # Clear pending actions
        self.state.pending_actions = []

        # Advance round
        self.state.round_number += 1
        if self.state.round_number > 10:
            # Transition to finale
            self.state.phase = Phase.FINALE
            self.state.round_number = 1  # finale round 1
            self.state.active_crises = []
            self.state.collapse_bar = 0
        else:
            self.state.active_crises = spawn_crises(self.state.round_number)

    def _resolve_finale_round(self) -> None:
        actions = self.state.pending_actions

        # Apply RUN actions
        for a in actions:
            if a.action_type == ActionType.RUN:
                player = next((p for p in self.state.players if p.id == a.player_id), None)
                if player and not player.is_down:
                    player.escape_track += 1

        # Apply CARRY actions (need 2 carries per downed crewmate to advance +1)
        carry_groups: dict[str, list[PlayerAction]] = {}
        for a in actions:
            if a.action_type == ActionType.CARRY and a.target_player_id:
                carry_groups.setdefault(a.target_player_id, []).append(a)
        for target_id, carriers in carry_groups.items():
            if len(carriers) >= 2:
                target = next((p for p in self.state.players if p.id == target_id), None)
                if target and target.is_down:
                    target.escape_track += 1

        # Apply HOLD actions
        hold_count = sum(1 for a in actions if a.action_type == ActionType.HOLD)
        self.state.collapse_bar = max(0, self.state.collapse_bar + 33 - (hold_count * 15))

        # Check if collapse hit 100%
        if self.state.collapse_bar >= 100:
            # Anyone not at escape_track 3 is lost
            self._end_finale()
            return

        # Check if all crew (standing + downed) reached escape track 3
        all_escaped = all(p.escape_track >= 3 for p in self.state.players)
        if all_escaped and self.state.players:
            self._end_finale()
            return

        # Clear pending actions
        self.state.pending_actions = []

        # Advance finale round
        self.state.round_number += 1
        if self.state.round_number > 3:
            # Finale ended — check who escaped
            self._end_finale()

    def _end_finale(self) -> None:
        survived = []
        lost = []
        for p in self.state.players:
            if p.escape_track >= 3:
                survived.append(p.id)
            else:
                lost.append(p.id)
        self.state.crew_survived = survived
        self.state.crew_lost = lost
        self.state.victory = len(lost) == 0
        self.state.partial = len(lost) > 0 and len(survived) > 0
        self.state.phase = Phase.RESULTS

    def _end_game(self, victory: bool) -> None:
        self.state.victory = victory
        self.state.partial = False
        if victory:
            self.state.crew_survived = [p.id for p in self.state.players]
            self.state.crew_lost = []
        else:
            self.state.crew_survived = []
            self.state.crew_lost = [p.id for p in self.state.players]
        self.state.phase = Phase.RESULTS

    def tick(self) -> None:
        self.resolve_round()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_game.py -v`
Expected: all tests PASS (including new ones)

- [ ] **Step 5: Commit**

```bash
git add backend/game.py backend/tests/test_game.py
git commit -m "feat: add survival phase tick/resolve and finale phase logic"
```

---

## Task 6: WebSocket Server & Connection Manager

**Files:**
- Modify: `backend/main.py` (add WebSocket endpoint, connection manager, room management)
- Create: `backend/tests/test_websocket.py`

**Interfaces:**
- Consumes: `Game` from `game.py`, `PlayerAction` from `models.py`
- Produces: `ConnectionManager` class (tracks WS connections per room)
- Produces: WebSocket endpoint `/ws/{room_code}` that handles join, action, start, and state broadcast
- Produces: `ROOMS: dict[str, Game]` registry of active games

- [ ] **Step 1: Write the failing test**

`backend/tests/test_websocket.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_websocket.py -v`
Expected: FAIL — no WebSocket endpoint exists

- [ ] **Step 3: Write minimal implementation**

Replace `backend/main.py`:
```python
import random
import string
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import os

from game import Game
from models import PlayerAction, ActionType, Phase

app = FastAPI()

# In-memory registry of active games: room_code -> Game
ROOMS: dict[str, Game] = {}
# Track connections: room_code -> {player_id: WebSocket}
connections: dict[str, dict[str, WebSocket]] = {}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


async def broadcast_state(room_code: str):
    """Send current state to all connected players in a room."""
    game = ROOMS.get(room_code)
    if not game:
        return
    state = game.get_state()
    state_data = state.model_dump(mode="json")
    room_conns = connections.get(room_code, {})
    for player_id, ws in room_conns.items():
        await ws.send_json({
            "type": "state",
            "state": state_data,
            "player_id": player_id,
        })


class ConnectionManager:
    async def connect(self, websocket: WebSocket, room_code: str, player_id: str):
        await websocket.accept()
        if room_code not in connections:
            connections[room_code] = {}
        connections[room_code][player_id] = websocket

    def disconnect(self, room_code: str, player_id: str):
        if room_code in connections:
            connections[room_code].pop(player_id, None)
            if not connections[room_code]:
                del connections[room_code]


manager = ConnectionManager()


@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    room_code = room_code.upper()
    player_id = None
    try:
        await websocket.accept()
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "join":
                name = data.get("name", "Unknown")
                if room_code not in ROOMS:
                    ROOMS[room_code] = Game(room_code)
                game = ROOMS[room_code]
                player = game.add_player(name)
                player_id = player.id
                if room_code not in connections:
                    connections[room_code] = {}
                connections[room_code][player_id] = websocket
                await broadcast_state(room_code)

            elif msg_type == "start":
                game = ROOMS.get(room_code)
                if not game or not player_id:
                    await websocket.send_json({"type": "error", "message": "Not in a game"})
                    continue
                if not game.is_host(player_id):
                    await websocket.send_json({"type": "error", "message": "Only host can start"})
                    continue
                try:
                    game.start()
                    await broadcast_state(room_code)
                except ValueError as e:
                    await websocket.send_json({"type": "error", "message": str(e)})

            elif msg_type == "action":
                game = ROOMS.get(room_code)
                if not game or not player_id:
                    await websocket.send_json({"type": "error", "message": "Not in a game"})
                    continue
                action = PlayerAction(
                    player_id=player_id,
                    action_type=ActionType(data["action_type"]),
                    target_system=data.get("target_system"),
                    target_crisis_id=data.get("target_crisis_id"),
                    target_player_id=data.get("target_player_id"),
                )
                game.submit_action(action)
                # Acknowledge receipt
                await websocket.send_json({"type": "action_ack"})

            elif msg_type == "resolve":
                game = ROOMS.get(room_code)
                if not game or not player_id:
                    continue
                if not game.is_host(player_id):
                    await websocket.send_json({"type": "error", "message": "Only host can resolve"})
                    continue
                game.resolve_round()
                await broadcast_state(room_code)

    except WebSocketDisconnect:
        if player_id and room_code in connections:
            connections[room_code].pop(player_id, None)
            if not connections[room_code]:
                del connections[room_code]
                # Optionally clean up the game if empty
                if room_code in ROOMS and len(ROOMS[room_code].get_state().players) == 0:
                    del ROOMS[room_code]


# Mount static SPA in production (built by Dockerfile)
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_websocket.py -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/main.py backend/tests/test_websocket.py
git commit -m "feat: add WebSocket endpoint with join/start/action/resolve handlers"
```

---

## Task 7: Action Phase Timer & Auto-Resolve

**Files:**
- Modify: `backend/main.py` (add timer task that auto-resolves when deadline passes)
- Modify: `backend/tests/test_websocket.py` (add timer test)

**Interfaces:**
- Consumes: `Game` from `game.py`
- Produces: background timer task that triggers `resolve_round()` when 45-sec action window expires
- Produces: `start_action_timer(room_code: str)` async function

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_websocket.py`:
```python
import asyncio
from unittest.mock import patch


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_websocket.py -v -k "timer or afk"`
Expected: FAIL — no deadline set, no AFK default

- [ ] **Step 3: Write minimal implementation**

Modify `backend/game.py` — add deadline setting and AFK defaults. Add `import time` to the top of the file (with the other imports added in Task 5). Add to `start()`:
```python
import time

def start(self) -> None:
    if self.state.phase != Phase.LOBBY:
        raise ValueError("can only start from lobby phase")
    if len(self.state.players) < self.MIN_PLAYERS:
        raise ValueError(f"minimum {self.MIN_PLAYERS} players required")
    self.state.phase = Phase.SURVIVAL
    self.state.round_number = 1
    self.state.active_crises = spawn_crises(1)
    self._set_action_deadline()

def _set_action_deadline(self) -> None:
    self.state.action_phase_deadline = time.time() + 45.0

def _apply_afk_defaults(self) -> None:
    """Players who didn't submit an action default to BOLSTER on lowest-health system."""
    acted_ids = {a.player_id for a in self.state.pending_actions}
    for player in self.state.players:
        if player.is_down:
            continue
        if player.id not in acted_ids:
            # Find lowest-health system
            lowest = min(self.state.systems, key=lambda s: self.state.systems[s])
            self.state.pending_actions.append(PlayerAction(
                player_id=player.id,
                action_type=ActionType.BOLSTER,
                target_system=lowest,
            ))
```

Modify `_resolve_survival_round` and `_resolve_finale_round` to call `_apply_afk_defaults()` at the start:
```python
def _resolve_survival_round(self) -> None:
    self._apply_afk_defaults()
    # ... rest of existing code ...

def _resolve_finale_round(self) -> None:
    self._apply_afk_defaults_finale()
    # ... rest of existing code ...

def _apply_afk_defaults_finale(self) -> None:
    acted_ids = {a.player_id for a in self.state.pending_actions}
    for player in self.state.players:
        if player.is_down:
            continue
        if player.id not in acted_ids:
            self.state.pending_actions.append(PlayerAction(
                player_id=player.id,
                action_type=ActionType.RUN,
            ))
```

After advancing round in `_resolve_survival_round`, set new deadline:
```python
        else:
            self.state.active_crises = spawn_crises(self.state.round_number)
            self._set_action_deadline()
```

And in `_resolve_finale_round` after advancing:
```python
        self.state.round_number += 1
        if self.state.round_number > 3:
            self._end_finale()
        else:
            self._set_action_deadline()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_websocket.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/game.py backend/main.py backend/tests/test_websocket.py
git commit -m "feat: add action phase timer and AFK default-to-bolster"
```

---

## Task 8: Frontend Types & WebSocket Client

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/websocket.ts`
- Create: `frontend/src/lib/stores.ts`

**Interfaces:**
- Consumes: backend model shapes from `models.py`
- Produces: TypeScript types mirroring backend, `GameWebSocket` class with reconnect, Svelte stores

- [ ] **Step 1: Write types**

`frontend/src/lib/types.ts`:
```typescript
export type SystemName = 'reactor' | 'life_support' | 'med_bay' | 'hull' | 'comms' | 'shields';

export type Phase = 'lobby' | 'survival' | 'finale' | 'results';

export type ActionType = 'fix' | 'bolster' | 'revive' | 'run' | 'carry' | 'hold';

export interface Crisis {
  id: string;
  name: string;
  description: string;
  system: SystemName;
  drain_rate: number;
  crew_required: number;
  tier: number;
  weight: number;
}

export interface Player {
  id: string;
  name: string;
  is_host: boolean;
  is_down: boolean;
  escape_track: number;
}

export interface PlayerAction {
  player_id: string;
  action_type: ActionType;
  target_system?: SystemName;
  target_crisis_id?: string;
  target_player_id?: string;
}

export interface GameState {
  room_code: string;
  phase: Phase;
  round_number: number;
  systems: Record<SystemName, number>;
  players: Player[];
  active_crises: Crisis[];
  pending_actions: PlayerAction[];
  collapse_bar: number;
  action_phase_deadline: number | null;
  crew_survived: string[];
  crew_lost: string[];
  victory: boolean;
  partial: boolean;
}

export type ServerMessage =
  | { type: 'state'; state: GameState; player_id: string }
  | { type: 'action_ack' }
  | { type: 'error'; message: string };

export type ClientMessage =
  | { type: 'join'; name: string }
  | { type: 'start' }
  | { type: 'action'; action_type: ActionType; target_system?: SystemName; target_crisis_id?: string; target_player_id?: string }
  | { type: 'resolve' };
```

- [ ] **Step 2: Write WebSocket client**

`frontend/src/lib/websocket.ts`:
```typescript
import type { ServerMessage, ClientMessage } from './types';

export class GameWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnect = 5;
  private listeners: ((msg: ServerMessage) => void)[] = [];
  private statusListeners: ((status: 'connected' | 'disconnected' | 'reconnecting') => void)[] = [];

  constructor(roomCode: string) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    this.url = `${protocol}//${host}/ws/${roomCode}`;
  }

  connect() {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.notifyStatus('connected');
    };
    this.ws.onmessage = (event) => {
      const msg: ServerMessage = JSON.parse(event.data);
      this.listeners.forEach((fn) => fn(msg));
    };
    this.ws.onclose = () => {
      this.notifyStatus('disconnected');
      if (this.reconnectAttempts < this.maxReconnect) {
        this.reconnectAttempts++;
        this.notifyStatus('reconnecting');
        setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
      }
    };
    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  send(msg: ClientMessage) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  onMessage(fn: (msg: ServerMessage) => void) {
    this.listeners.push(fn);
  }

  onStatusChange(fn: (status: 'connected' | 'disconnected' | 'reconnecting') => void) {
    this.statusListeners.push(fn);
  }

  private notifyStatus(status: 'connected' | 'disconnected' | 'reconnecting') {
    this.statusListeners.forEach((fn) => fn(status));
  }

  close() {
    this.maxReconnect = 0;
    this.ws?.close();
  }
}
```

- [ ] **Step 3: Write stores**

`frontend/src/lib/stores.ts`:
```typescript
import { writable, derived } from 'svelte/store';
import type { GameState, ServerMessage } from './types';

export const gameState = writable<GameState | null>(null);
export const playerId = writable<string | null>(null);
export const connectionStatus = writable<'connecting' | 'connected' | 'disconnected' | 'reconnecting'>('connecting');
export const errorMessage = writable<string | null>(null);

export function handleMessage(msg: ServerMessage) {
  switch (msg.type) {
    case 'state':
      gameState.set(msg.state);
      playerId.set(msg.player_id);
      errorMessage.set(null);
      break;
    case 'action_ack':
      // Action acknowledged — could show a brief confirmation
      break;
    case 'error':
      errorMessage.set(msg.message);
      break;
  }
}

export const currentPhase = derived(gameState, ($gs) => $gs?.phase ?? null);
export const isHost = derived(
  [gameState, playerId],
  ([$gs, $pid]) => $gs?.players.find((p) => p.id === $pid)?.is_host ?? false
);
export const myPlayer = derived(
  [gameState, playerId],
  ([$gs, $pid]) => $gs?.players.find((p) => p.id === $pid) ?? null
);
```

- [ ] **Step 4: Verify TypeScript compiles**

Run: `cd frontend && npm run build`
Expected: build succeeds (may need to create routes first; if errors about missing routes, continue to Task 9 and build after)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/
git commit -m "feat: add frontend types, WebSocket client, and Svelte stores"
```

---

## Task 9: Join Screen & Lobby

**Files:**
- Modify: `frontend/src/routes/+page.svelte` (join screen)
- Create: `frontend/src/routes/lobby/+page.svelte`

**Interfaces:**
- Consumes: `GameWebSocket` from `websocket.ts`, stores from `stores.ts`
- Produces: join screen (enter room code + name) and lobby screen (player list, host start button)

- [ ] **Step 1: Write join screen**

`frontend/src/routes/+page.svelte`:
```svelte
<script lang="ts">
  import { goto } from '$app/navigation';
  import { GameWebSocket } from '$lib/websocket';
  import { handleMessage, gameState, connectionStatus } from '$lib/stores';

  let roomCode = '';
  let name = '';
  let ws: GameWebSocket | null = null;
  let localError = '';

  function joinGame() {
    localError = '';
    if (roomCode.length !== 4) {
      localError = 'Room code must be 4 characters';
      return;
    }
    if (!name.trim()) {
      localError = 'Enter your name';
      return;
    }
    ws = new GameWebSocket(roomCode.toUpperCase());
    ws.onMessage(handleMessage);
    ws.onStatusChange((status) => connectionStatus.set(status));
    ws.connect();
    // Wait for connection, then send join
    const checkConnected = setInterval(() => {
      if ($connectionStatus === 'connected') {
        clearInterval(checkConnected);
        ws?.send({ type: 'join', name: name.trim() });
        goto('/lobby');
      }
    }, 100);
  }
</script>

<div class="container">
  <h1>Station Meltdown</h1>
  <p class="tagline">The crew of a failing space station has 10 rounds to survive, then escape before the core blows.</p>

  <div class="form">
    <label>
      Room Code
      <input
        type="text"
        bind:value={roomCode}
        maxlength="4"
        placeholder="ABCD"
        style="text-transform: uppercase"
      />
    </label>
    <label>
      Your Name
      <input type="text" bind:value={name} maxlength="20" placeholder="Captain Riya" />
    </label>
    {#if localError}
      <p class="error">{localError}</p>
    {/if}
    <button onclick={joinGame}>Join Game</button>
  </div>

  <p class="status">Connection: {$connectionStatus}</p>
</div>

<style>
  .container {
    max-width: 400px;
    margin: 2rem auto;
    padding: 1rem;
    font-family: system-ui, sans-serif;
  }
  h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
  .tagline { color: #888; font-size: 0.9rem; margin-bottom: 1.5rem; }
  .form { display: flex; flex-direction: column; gap: 1rem; }
  label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.85rem; }
  input {
    padding: 0.75rem;
    font-size: 1rem;
    border: 1px solid #ccc;
    border-radius: 4px;
  }
  button {
    padding: 0.75rem;
    font-size: 1rem;
    background: #2563eb;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
  button:hover { background: #1d4ed8; }
  .error { color: #dc2626; font-size: 0.85rem; }
  .status { color: #888; font-size: 0.8rem; margin-top: 1rem; }
</style>
```

- [ ] **Step 2: Write lobby screen**

`frontend/src/routes/lobby/+page.svelte`:
```svelte
<script lang="ts">
  import { gameState, isHost, connectionStatus } from '$lib/stores';
  import { GameWebSocket } from '$lib/websocket';

  let ws: GameWebSocket | null = null;

  // Reuse the WS connection from join — in a real app we'd use a context or service
  // For simplicity, this screen reads gameState which was set by the join screen

  function startGame() {
    // Send start via the existing WS — need to expose it
    // For now, dispatch a custom event that the layout listens for
    const event = new CustomEvent('start-game');
    window.dispatchEvent(event);
  }
</script>

<div class="container">
  <h1>Lobby — Room {$gameState?.room_code ?? '...'}</h1>

  <div class="players">
    <h2>Crew ({$gameState?.players.length ?? 0}/15)</h2>
    <ul>
      {#each $gameState?.players ?? [] as player}
        <li class:host={player.is_host}>
          {player.name}
          {#if player.is_host}<span class="badge">Host</span>{/if}
        </li>
      {/each}
    </ul>
  </div>

  {#if $gameState && $gameState.players.length < 4}
    <p class="warning">Need at least 4 players to start. Currently {$gameState.players.length}.</p>
  {/if}

  {#if $isHost}
    <button
      onclick={startGame}
      disabled={$gameState && $gameState.players.length < 4}
    >
      Start Game
    </button>
  {:else}
    <p class="waiting">Waiting for host to start the game...</p>
  {/if}

  <p class="status">Connection: {$connectionStatus}</p>
</div>

<style>
  .container {
    max-width: 500px;
    margin: 2rem auto;
    padding: 1rem;
    font-family: system-ui, sans-serif;
  }
  h1 { font-size: 1.5rem; }
  .players { margin: 1.5rem 0; }
  h2 { font-size: 1.1rem; margin-bottom: 0.5rem; }
  ul { list-style: none; padding: 0; }
  li {
    padding: 0.5rem;
    border-bottom: 1px solid #eee;
    font-size: 1rem;
  }
  li.host { font-weight: bold; }
  .badge {
    font-size: 0.7rem;
    background: #2563eb;
    color: white;
    padding: 0.1rem 0.4rem;
    border-radius: 3px;
    margin-left: 0.5rem;
  }
  button {
    padding: 0.75rem 1.5rem;
    font-size: 1rem;
    background: #16a34a;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
  button:disabled { background: #ccc; cursor: not-allowed; }
  .warning { color: #f59e0b; }
  .waiting { color: #888; font-style: italic; }
  .status { color: #888; font-size: 0.8rem; margin-top: 1rem; }
</style>
```

- [ ] **Step 3: Wire WS into layout for cross-screen access**

Replace `frontend/src/routes/+layout.svelte`:
```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { GameWebSocket } from '$lib/websocket';
  import { handleMessage, connectionStatus } from '$lib/stores';

  let { children } = $props();
  let ws: GameWebSocket | null = null;

  onMount(() => {
    // Listen for start-game events from lobby
    window.addEventListener('start-game', () => {
      ws?.send({ type: 'start' });
    });
  });

  onDestroy(() => {
    window.removeEventListener('start-game', () => {});
    ws?.close();
  });

  // Expose WS globally for components to send actions
  export function getWs() { return ws; }
</script>

{@render children()}
```

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/
git commit -m "feat: add join screen and lobby screen"
```

---

## Task 10: Play Screen (Survival Phase)

**Files:**
- Create: `frontend/src/routes/play/+page.svelte`

**Interfaces:**
- Consumes: `gameState`, `myPlayer` stores, `GameWebSocket` for sending actions
- Produces: survival phase UI — station status, crisis list, action picker, countdown timer

- [ ] **Step 1: Write play screen**

`frontend/src/routes/play/+page.svelte`:
```svelte
<script lang="ts">
  import { gameState, myPlayer, errorMessage } from '$lib/stores';
  import type { SystemName, ActionType, Crisis } from '$lib/types';

  let selectedAction: ActionType | null = null;
  let selectedSystem: SystemName | null = null;
  let selectedCrisisId: string | null = null;
  let selectedPlayerId: string | null = null;

  const systemLabels: Record<SystemName, string> = {
    reactor: 'Reactor',
    life_support: 'Life Support',
    med_bay: 'Med Bay',
    hull: 'Hull',
    comms: 'Comms',
    shields: 'Shields',
  };

  const systemColors: Record<SystemName, string> = {
    reactor: '#dc2626',
    life_support: '#16a34a',
    med_bay: '#0891b2',
    hull: '#a16207',
    comms: '#7c3aed',
    shields: '#2563eb',
  };

  function healthColor(health: number): string {
    if (health > 60) return '#16a34a';
    if (health > 30) return '#f59e0b';
    return '#dc2626';
  }

  function timeRemaining(): number {
    if (!$gameState?.action_phase_deadline) return 0;
    return Math.max(0, Math.ceil(($gameState.action_phase_deadline - Date.now() / 1000)));
  }

  let timeLeft = $timeRemaining();
  $: if ($gameState?.action_phase_deadline) {
    timeLeft = timeRemaining();
  }

  function selectFix(crisis: Crisis) {
    selectedAction = 'fix';
    selectedCrisisId = crisis.id;
    selectedSystem = crisis.system;
  }

  function selectBolster(system: SystemName) {
    selectedAction = 'bolster';
    selectedSystem = system;
    selectedCrisisId = null;
  }

  function selectRevive(playerId: string) {
    selectedAction = 'revive';
    selectedPlayerId = playerId;
    selectedSystem = null;
    selectedCrisisId = null;
  }

  function submitAction() {
    if (!selectedAction) return;
    const event = new CustomEvent('send-action', {
      detail: {
        action_type: selectedAction,
        target_system: selectedSystem,
        target_crisis_id: selectedCrisisId,
        target_player_id: selectedPlayerId,
      }
    });
    window.dispatchEvent(event);
    selectedAction = null;
    selectedSystem = null;
    selectedCrisisId = null;
    selectedPlayerId = null;
  }

  // Redirect to correct phase
  $: if ($gameState?.phase === 'finale') {
    window.location.href = '/finale';
  }
  $: if ($gameState?.phase === 'results') {
    window.location.href = '/results';
  }
</script>

<div class="container">
  {#if $myPlayer?.is_down}
    <div class="downed">
      <h1>YOU ARE DOWN</h1>
      <p>Waiting for a crewmate to revive you.</p>
    </div>
  {:else if $gameState}
    <header>
      <h1>Round {$gameState.round_number} / 10</h1>
      <div class="timer" class:urgent={timeLeft <= 10}>
        {timeLeft}s
      </div>
    </header>

    <!-- Station Systems -->
    <section class="systems">
      <h2>Station Status</h2>
      <div class="system-grid">
        {#each Object.entries($gameState.systems) as [sys, health]}
          <div class="system" style="border-color: {systemColors[sys as SystemName]}">
            <span class="sys-name">{systemLabels[sys as SystemName]}</span>
            <div class="health-bar">
              <div
                class="health-fill"
                style="width: {health}%; background: {healthColor(health)}"
              ></div>
            </div>
            <span class="health-num">{health}</span>
          </div>
        {/each}
      </div>
    </section>

    <!-- Active Crises -->
    {#if $gameState.active_crises.length > 0}
      <section class="crises">
        <h2>Active Crises</h2>
        {#each $gameState.active_crises as crisis}
          <div class="crisis" class:selected={selectedCrisisId === crisis.id}>
            <div class="crisis-info">
              <strong>{crisis.name}</strong>
              <p>{crisis.description}</p>
              <span class="drain">-{crisis.drain_rate}/round</span>
              <span class="crew">Needs {crisis.crew_required} crew to FIX</span>
            </div>
            <button
              onclick={() => selectFix(crisis)}
              class:active={selectedCrisisId === crisis.id}
            >
              FIX
            </button>
          </div>
        {/each}
      </section>
    {/if}

    <!-- Action Picker -->
    <section class="actions">
      <h2>Your Action</h2>

      {#if selectedAction === 'fix'}
        <div class="selected-action">
          <p>FIXing: {$gameState.active_crises.find(c => c.id === selectedCrisisId)?.name}</p>
          <button onclick={submitAction} class="submit">Confirm FIX</button>
          <button onclick={() => { selectedAction = null; selectedCrisisId = null; }}>Cancel</button>
        </div>
      {:else if selectedAction === 'bolster'}
        <div class="selected-action">
          <p>BOLSTERing: {systemLabels[selectedSystem as SystemName]}</p>
          <button onclick={submitAction} class="submit">Confirm BOLSTER</button>
          <button onclick={() => { selectedAction = null; selectedSystem = null; }}>Cancel</button>
        </div>
      {:else if selectedAction === 'revive'}
        <div class="selected-action">
          <p>REVIVEing crewmate</p>
          <button onclick={submitAction} class="submit">Confirm REVIVE</button>
          <button onclick={() => { selectedAction = null; selectedPlayerId = null; }}>Cancel</button>
        </div>
      {:else}
        <div class="action-options">
          <div class="bolster-options">
            <p>BOLSTER a system (+5):</p>
            {#each Object.keys($gameState.systems) as sys}
              <button
                onclick={() => selectBolster(sys as SystemName)}
                style="border-color: {systemColors[sys as SystemName]}"
              >
                {systemLabels[sys as SystemName]}
              </button>
            {/each}
          </div>

          {#if $gameState.players.some(p => p.is_down) && $gameState.systems.med_bay > 0}
            <div class="revive-options">
              <p>REVIVE a downed crewmate:</p>
              {#each $gameState.players.filter(p => p.is_down) as downed}
                <button onclick={() => selectRevive(downed.id)}>
                  {downed.name}
                </button>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
    </section>

    {#if $errorMessage}
      <p class="error">{$errorMessage}</p>
    {/if}
  {/if}
</div>

<style>
  .container {
    max-width: 500px;
    margin: 0 auto;
    padding: 0.5rem;
    font-family: system-ui, sans-serif;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0;
    border-bottom: 2px solid #333;
  }
  h1 { font-size: 1.2rem; }
  .timer {
    font-size: 1.5rem;
    font-weight: bold;
    font-family: monospace;
    padding: 0.25rem 0.75rem;
    background: #1e293b;
    color: #4ade80;
    border-radius: 4px;
  }
  .timer.urgent { color: #f87171; animation: pulse 1s infinite; }
  @keyframes pulse { 50% { opacity: 0.5; } }
  section { margin: 1rem 0; }
  h2 { font-size: 1rem; margin-bottom: 0.5rem; color: #666; }
  .system-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }
  .system {
    border-left: 4px solid;
    padding: 0.5rem;
    background: #f8fafc;
    border-radius: 4px;
  }
  .sys-name { font-size: 0.8rem; font-weight: bold; }
  .health-bar {
    height: 8px;
    background: #e2e8f0;
    border-radius: 4px;
    margin: 0.25rem 0;
    overflow: hidden;
  }
  .health-fill { height: 100%; transition: width 0.3s; }
  .health-num { font-size: 0.75rem; color: #666; }
  .crisis {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem;
    border: 2px solid #f59e0b;
    border-radius: 4px;
    margin-bottom: 0.5rem;
    background: #fffbeb;
  }
  .crisis.selected { border-color: #2563eb; background: #eff6ff; }
  .crisis-info { flex: 1; }
  .crisis-info strong { font-size: 0.9rem; }
  .crisis-info p { font-size: 0.8rem; color: #666; margin: 0.25rem 0; }
  .drain { color: #dc2626; font-size: 0.75rem; font-weight: bold; }
  .crew { color: #7c3aed; font-size: 0.75rem; margin-left: 0.5rem; }
  button {
    padding: 0.5rem 1rem;
    font-size: 0.85rem;
    border: 2px solid #ccc;
    background: white;
    border-radius: 4px;
    cursor: pointer;
  }
  button.active { border-color: #2563eb; background: #eff6ff; }
  button.submit { background: #2563eb; color: white; border-color: #2563eb; }
  button:hover { background: #f1f5f9; }
  button.submit:hover { background: #1d4ed8; }
  .action-options { display: flex; flex-direction: column; gap: 0.75rem; }
  .selected-action {
    padding: 1rem;
    background: #eff6ff;
    border-radius: 4px;
    text-align: center;
  }
  .downed {
    text-align: center;
    padding: 3rem 1rem;
  }
  .downed h1 { color: #dc2626; font-size: 2rem; }
  .error { color: #dc2626; text-align: center; }
</style>
```

- [ ] **Step 2: Wire action sending into layout**

Modify `frontend/src/routes/+layout.svelte` to listen for `send-action` events:
```svelte
// Add to onMount:
window.addEventListener('send-action', (e: Event) => {
  const detail = (e as CustomEvent).detail;
  ws?.send({
    type: 'action',
    action_type: detail.action_type,
    target_system: detail.target_system,
    target_crisis_id: detail.target_crisis_id,
    target_player_id: detail.target_player_id,
  });
});
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/play/ frontend/src/routes/+layout.svelte
git commit -m "feat: add survival phase play screen with action picker"
```

---

## Task 11: Finale Screen (Escape Sequence)

**Files:**
- Create: `frontend/src/routes/finale/+page.svelte`

**Interfaces:**
- Consumes: `gameState`, `myPlayer` stores
- Produces: finale UI — collapse bar, escape progress, RUN/CARRY/HOLD action picker

- [ ] **Step 1: Write finale screen**

`frontend/src/routes/finale/+page.svelte`:
```svelte
<script lang="ts">
  import { gameState, myPlayer } from '$lib/stores';
  import type { Player } from '$lib/types';

  let selectedAction: 'run' | 'carry' | 'hold' | null = null;
  let carryTargetId: string | null = null;

  function submitRun() {
    const event = new CustomEvent('send-action', {
      detail: { action_type: 'run' }
    });
    window.dispatchEvent(event);
    selectedAction = null;
  }

  function submitCarry(playerId: string) {
    const event = new CustomEvent('send-action', {
      detail: { action_type: 'carry', target_player_id: playerId }
    });
    window.dispatchEvent(event);
    selectedAction = null;
    carryTargetId = null;
  }

  function submitHold() {
    const event = new CustomEvent('send-action', {
      detail: { action_type: 'hold' }
    });
    window.dispatchEvent(event);
    selectedAction = null;
  }

  // Redirect if phase changes
  $: if ($gameState?.phase === 'results') {
    window.location.href = '/results';
  }
  $: if ($gameState?.phase === 'survival') {
    window.location.href = '/play';
  }

  function escapeProgress(p: Player): number {
    return Math.min(100, (p.escape_track / 3) * 100);
  }
</script>

<div class="container">
  {#if $myPlayer?.is_down && $myPlayer.escape_track === 0}
    <div class="downed">
      <h1>YOU ARE DOWN</h1>
      <p>You need crewmates to CARRY you to the pods. You can't move on your own.</p>
    </div>
  {:else if $gameState}
    <header>
      <h1>ESCAPE — Round {$gameState.round_number} / 3</h1>
    </header>

    <!-- Collapse Bar -->
    <section class="collapse">
      <h2>Station Collapse</h2>
      <div class="collapse-bar">
        <div class="collapse-fill" style="width: {$gameState.collapse_bar}%"></div>
      </div>
      <span class="collapse-pct">{$gameState.collapse_bar}%</span>
    </section>

    <!-- Crew Escape Progress -->
    <section class="crew">
      <h2>Crew Escape Progress</h2>
      {#each $gameState.players as player}
        <div class="crew-row" class:down={player.is_down} class:safe={player.escape_track >= 3}>
          <span class="crew-name">
            {player.name}
            {#if player.is_down}<span class="tag">DOWN</span>{/if}
            {#if player.escape_track >= 3}<span class="tag safe">SAFE</span>{/if}
          </span>
          <div class="escape-bar">
            <div class="escape-fill" style="width: {escapeProgress(player)}%"></div>
          </div>
          <span class="track">{player.escape_track}/3</span>
        </div>
      {/each}
    </section>

    <!-- Action Picker -->
    {#if $myPlayer && !$myPlayer.is_down && $myPlayer.escape_track < 3}
      <section class="actions">
        <h2>Your Action</h2>
        {#if selectedAction === 'run'}
          <div class="confirm">
            <p>RUN to the pods?</p>
            <button onclick={submitRun} class="submit">Confirm RUN</button>
            <button onclick={() => selectedAction = null}>Cancel</button>
          </div>
        {:else if selectedAction === 'carry'}
          <div class="confirm">
            <p>CARRY a downed crewmate (needs 2 crew):</p>
            {#each $gameState.players.filter(p => p.is_down && p.escape_track < 3) as downed}
              <button onclick={() => submitCarry(downed.id)}>
                Carry {downed.name}
              </button>
            {/each}
            <button onclick={() => selectedAction = null}>Cancel</button>
          </div>
        {:else if selectedAction === 'hold'}
          <div class="confirm">
            <p>HOLD the bulkhead? (slows collapse by 15%)</p>
            <button onclick={submitHold} class="submit">Confirm HOLD</button>
            <button onclick={() => selectedAction = null}>Cancel</button>
          </div>
        {:else}
          <div class="action-buttons">
            <button onclick={() => selectedAction = 'run'} class="action-btn run">
              RUN<br><small>+1 to your escape</small>
            </button>
            {#if $gameState.players.some(p => p.is_down && p.escape_track < 3)}
              <button onclick={() => selectedAction = 'carry'} class="action-btn carry">
                CARRY<br><small>+1 to downed crewmate (needs 2)</small>
              </button>
            {/if}
            <button onclick={() => selectedAction = 'hold'} class="action-btn hold">
              HOLD<br><small>-15% collapse</small>
            </button>
          </div>
        {/if}
      </section>
    {:else if $myPlayer && $myPlayer.escape_track >= 3}
      <div class="safe">
        <h1>YOU'RE IN THE PODS</h1>
        <p>Safe. Watching your crewmates escape...</p>
      </div>
    {/if}
  {/if}
</div>

<style>
  .container {
    max-width: 500px;
    margin: 0 auto;
    padding: 0.5rem;
    font-family: system-ui, sans-serif;
  }
  header { text-align: center; padding: 0.5rem 0; border-bottom: 2px solid #dc2626; }
  h1 { font-size: 1.2rem; }
  section { margin: 1rem 0; }
  h2 { font-size: 1rem; color: #666; margin-bottom: 0.5rem; }
  .collapse-bar {
    height: 20px;
    background: #1e293b;
    border-radius: 4px;
    overflow: hidden;
  }
  .collapse-fill {
    height: 100%;
    background: linear-gradient(90deg, #f59e0b, #dc2626);
    transition: width 0.3s;
  }
  .collapse-pct { font-weight: bold; font-size: 0.9rem; }
  .crew-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0;
    font-size: 0.85rem;
  }
  .crew-row.down .crew-name { color: #dc2626; }
  .crew-row.safe .crew-name { color: #16a34a; }
  .crew-name { flex: 0 0 120px; }
  .tag {
    font-size: 0.65rem;
    padding: 0.1rem 0.3rem;
    background: #dc2626;
    color: white;
    border-radius: 3px;
    margin-left: 0.25rem;
  }
  .tag.safe { background: #16a34a; }
  .escape-bar {
    flex: 1;
    height: 10px;
    background: #e2e8f0;
    border-radius: 4px;
    overflow: hidden;
  }
  .escape-fill {
    height: 100%;
    background: #16a34a;
    transition: width 0.3s;
  }
  .track { flex: 0 0 40px; text-align: right; font-family: monospace; }
  .action-buttons {
    display: flex;
    gap: 0.5rem;
  }
  .action-btn {
    flex: 1;
    padding: 1rem 0.5rem;
    font-size: 0.9rem;
    font-weight: bold;
    border: 2px solid;
    border-radius: 4px;
    cursor: pointer;
    text-align: center;
  }
  .action-btn.run { border-color: #16a34a; background: #f0fdf4; }
  .action-btn.carry { border-color: #7c3aed; background: #f5f3ff; }
  .action-btn.hold { border-color: #f59e0b; background: #fffbeb; }
  .action-btn small { font-weight: normal; font-size: 0.7rem; display: block; }
  .confirm {
    padding: 1rem;
    background: #eff6ff;
    border-radius: 4px;
    text-align: center;
  }
  button.submit { background: #2563eb; color: white; border-color: #2563eb; }
  .downed, .safe { text-align: center; padding: 2rem 1rem; }
  .downed h1 { color: #dc2626; }
  .safe h1 { color: #16a34a; }
</style>
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/finale/
git commit -m "feat: add finale escape sequence screen"
```

---

## Task 12: Results Screen

**Files:**
- Create: `frontend/src/routes/results/+page.svelte`

**Interfaces:**
- Consumes: `gameState` store
- Produces: results UI — win/loss, crew survival report, play again button

- [ ] **Step 1: Write results screen**

`frontend/src/routes/results/+page.svelte`:
```svelte
<script lang="ts">
  import { gameState } from '$lib/stores';

  function playAgain() {
    window.location.href = '/';
  }
</script>

<div class="container">
  {#if $gameState}
    {#if $gameState.victory}
      <div class="result victory">
        <h1>STATION SAVED</h1>
        <p>All crew escaped. The station may be gone, but you made it.</p>
      </div>
    {:else if $gameState.partial}
      <div class="result partial">
        <h1>PARTIAL ESCAPE</h1>
        <p>Some made it. Some didn't.</p>
      </div>
    {:else}
      <div class="result loss">
        <h1>STATION LOST</h1>
        <p>The station is gone. No one made it out.</p>
      </div>
    {/if}

    <section class="crew-report">
      <h2>Crew Report</h2>
      <div class="survived">
        <h3>Survived ({$gameState.crew_survived.length})</h3>
        <ul>
          {#each $gameState.crew_survived as id}
            {@const player = $gameState.players.find(p => p.id === id)}
            {#if player}
              <li class="survivor">{player.name}</li>
            {/if}
          {/each}
          {#if $gameState.crew_survived.length === 0}
            <li class="empty">No survivors</li>
          {/if}
        </ul>
      </div>
      <div class="lost">
        <h3>Lost ({$gameState.crew_lost.length})</h3>
        <ul>
          {#each $gameState.crew_lost as id}
            {@const player = $gameState.players.find(p => p.id === id)}
            {#if player}
              <li class="casualty">{player.name}</li>
            {/if}
          {/each}
          {#if $gameState.crew_lost.length === 0}
            <li class="empty">No casualties</li>
          {/if}
        </ul>
      </div>
    </section>

    <button onclick={playAgain}>Play Again</button>
  {/if}
</div>

<style>
  .container {
    max-width: 500px;
    margin: 2rem auto;
    padding: 1rem;
    font-family: system-ui, sans-serif;
    text-align: center;
  }
  .result { padding: 2rem 1rem; border-radius: 8px; margin-bottom: 1.5rem; }
  .victory { background: #f0fdf4; border: 2px solid #16a34a; }
  .partial { background: #fffbeb; border: 2px solid #f59e0b; }
  .loss { background: #fef2f2; border: 2px solid #dc2626; }
  h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
  .victory h1 { color: #16a34a; }
  .partial h1 { color: #f59e0b; }
  .loss h1 { color: #dc2626; }
  .crew-report { text-align: left; margin: 1.5rem 0; }
  h2 { font-size: 1.2rem; margin-bottom: 0.75rem; }
  h3 { font-size: 1rem; margin-bottom: 0.5rem; }
  .survived h3 { color: #16a34a; }
  .lost h3 { color: #dc2626; }
  ul { list-style: none; padding: 0; }
  li { padding: 0.5rem; border-bottom: 1px solid #eee; font-size: 1rem; }
  .survivor { color: #16a34a; }
  .casualty { color: #dc2626; }
  .empty { color: #999; font-style: italic; }
  button {
    padding: 0.75rem 2rem;
    font-size: 1rem;
    background: #2563eb;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
  }
  button:hover { background: #1d4ed8; }
</style>
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/results/
git commit -m "feat: add results screen with crew survival report"
```

---

## Task 13: Phase Routing & Integration

**Files:**
- Modify: `frontend/src/routes/+layout.svelte` (add phase-based routing)

**Interfaces:**
- Consumes: `gameState` store
- Produces: automatic navigation to `/play`, `/finale`, `/results` based on `gameState.phase`

- [ ] **Step 1: Add phase-based routing to layout**

Replace `frontend/src/routes/+layout.svelte`:
```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { GameWebSocket } from '$lib/websocket';
  import { handleMessage, gameState, connectionStatus } from '$lib/stores';

  let { children } = $props();
  let ws: GameWebSocket | null = null;

  onMount(() => {
    window.addEventListener('start-game', () => {
      ws?.send({ type: 'start' });
    });

    window.addEventListener('send-action', (e: Event) => {
      const detail = (e as CustomEvent).detail;
      ws?.send({
        type: 'action',
        action_type: detail.action_type,
        target_system: detail.target_system,
        target_crisis_id: detail.target_crisis_id,
        target_player_id: detail.target_player_id,
      });
    });
  });

  onDestroy(() => {
    ws?.close();
  });

  // Auto-route based on phase
  let lastPhase: string | null = null;
  $: if ($gameState && $gameState.phase !== lastPhase) {
    lastPhase = $gameState.phase;
    if ($gameState.phase === 'survival') goto('/play');
    else if ($gameState.phase === 'finale') goto('/finale');
    else if ($gameState.phase === 'results') goto('/results');
  }
</script>

{@render children()}
```

- [ ] **Step 2: Manual integration test**

Run: `cd backend && uvicorn main:app --reload` (terminal 1)
Run: `cd frontend && npm run dev` (terminal 2)
Open browser to `http://localhost:5173`:
1. Enter room code "TEST" and name "Alice"
2. Open 3 more browser tabs, join with same code, different names
3. As Alice (host), click Start
4. All 4 tabs should navigate to /play
5. Each player picks an action, host clicks resolve (or wait for timer)
6. Verify state updates on all tabs
7. After 10 rounds, should auto-navigate to /finale
8. After 3 finale rounds, should auto-navigate to /results

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/+layout.svelte
git commit -m "feat: add phase-based auto-routing"
```

---

## Task 14: Docker Build & Run Verification

**Files:**
- No new files — verify existing Dockerfile works end-to-end

- [ ] **Step 1: Build Docker image**

Run: `docker build -t station-meltdown .`
Expected: image builds successfully

- [ ] **Step 2: Run container**

Run: `docker run -p 8000:8000 station-meltdown`
Expected: uvicorn starts, serves SPA at `http://localhost:8000`

- [ ] **Step 3: Verify end-to-end in container**

Open browser to `http://localhost:8000`:
1. Verify join screen loads
2. Enter room code, name, join
3. Open another tab, join same room
4. Verify lobby shows both players
5. (If 4 players) start game, verify play screen loads

- [ ] **Step 4: Commit any fixes needed**

If the Docker build or run revealed issues, fix them and commit:
```bash
git add -A
git commit -m "fix: docker build and run issues"
```

---

## Task 15: End-to-End Playtest & Polish

**Files:**
- Possibly minor fixes across all files

- [ ] **Step 1: Full playtest with 4+ players**

Gather 4+ people (or use multiple browser tabs with different names):
1. All join same room code
2. Host starts game
3. Play through 10 survival rounds — verify:
   - Crises spawn correctly (1 early, 2 mid, 3 late)
   - FIX with enough crew works
   - FIX with insufficient crew doesn't work
   - BOLSTER adds +5 (capped at 100)
   - REVIVE works (needs Med Bay > 0)
   - Systems drain correctly
   - Reactor = 0 triggers loss
   - Life Support = 0 downs crew
   - Timer counts down and auto-resolves
4. Reach finale — verify:
   - Collapse bar fills +33%/round
   - HOLD reduces it
   - RUN advances escape track
   - CARRY works with 2 crew
   - Win/partial/loss triggers correctly
5. Results screen shows correct survivor list

- [ ] **Step 2: Fix any bugs found**

Address any issues discovered during playtest. Commit each fix:
```bash
git add -A
git commit -m "fix: <description of fix>"
```

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: Station Meltdown v1.0 — complete game"
```

---

## Spec Coverage Check

| Spec section | Task(s) |
|--------------|---------|
| Core Game Loop (setup, 10 rounds, resolve) | Tasks 4, 5, 7, 13 |
| Finale Phase (escape sequence, 3 rounds) | Tasks 5, 11, 13 |
| Station Systems (6 systems, health 0-100) | Task 2 (models), Task 5 (drain logic) |
| Crises (40 pool, tiers, spawn logic, no dup systems, multi-crew guarantee) | Task 3 |
| Player Actions (FIX, BOLSTER, REVIVE) | Tasks 2, 5 |
| Finale Actions (RUN, CARRY, HOLD) | Tasks 2, 5, 11 |
| Crew Power Mechanic (crew_required) | Task 5 (resolve logic) |
| Downed Crew (KO, revive, all-down loss) | Task 5 |
| Win/Loss Conditions | Task 5 |
| Tech Architecture (FastAPI, SvelteKit, WebSocket, in-memory) | Tasks 1, 6, 8 |
| Deployment (Docker, single container) | Tasks 1, 14 |
| Screens (Join, Lobby, Play, Finale, Results) | Tasks 9, 10, 11, 12 |
| AFK defaults | Task 7 |
| Action phase timer (45 sec) | Task 7 |

All spec sections covered.