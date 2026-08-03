# Station Meltdown — Design Spec

**Date:** 2026-08-03
**Status:** Approved (brainstorming phase)
**Next step:** Implementation plan via writing-plans skill

---

## Summary

A co-op sci-fi survival game for up to 15 players, played on personal devices via a web app. The crew of a failing space station has 10 rounds to endure escalating crises, then a 3-round escape sequence to reach the pods before the station collapses. Fully automated — the app is the game master. Procedurally generated crises every session. 30-minute hard session cap.

---

## Core Game Loop

### Setup (~30 sec)
- Host creates a game, receives a 4-letter join code.
- Players join via browser on their phones by entering the code + their name.
- App assigns all players as "crew."
- Host clicks Start.

### Survival Phase: 10 Rounds (~12-13 min)

Each round (~75 sec):

| Phase | Duration | What happens |
|-------|----------|--------------|
| Status | ~5 sec | App broadcasts station state: systems + health, active crises, crew status (up/down), round number |
| Action | 45 sec | Each player picks ONE action from their device. Live countdown. Can change selection until lock. |
| Resolve | ~10 sec | App computes all actions simultaneously, broadcasts results per crisis/system |
| Advance | ~15 sec | Clock ticks forward, new crises spawn, next round begins |

**Key properties:**
- All players act simultaneously — no turns, no waiting.
- 45 sec action window gives 15 players enough time to read options and decide.
- Resolve is instant — app computes, no debate or voting phase.
- 10 rounds create the narrative arc: early calm → mid chaos → late desperation.

### Finale Phase: Escape Sequence (~5 min)

Triggered after round 10 if the station survived (reactor > 0, at least 1 crew alive).

3 rounds, ~90 sec each. No new crises spawn — pure objective race.

**Goal:** Get all surviving crew to the escape pods before the collapse bar hits 100%.

**Escape progress:** Each crew member has an escape track of 0-3. Each round they take an action that advances their track by 1 (RUN) or is advanced by others (CARRY). When a crew member's track reaches 3, they're in the pods — safe.

**Collapse bar:** Starts at 0. Fills +33% per round. Reaches 100% at end of round 3. HOLD actions reduce it by ~15% (so 2 HOLDs per round can keep it below 100% through round 3, buying time).

**Each round, players pick one:**
- **RUN** — advance your own escape track by 1 (progress toward pods)
- **CARRY** — advance a downed crewmate's escape track by 1 (requires 2 players to CARRY the same crewmate; each contributes)
- **HOLD** — seal a bulkhead, reduces collapse bar by ~15%

**Downed crew in finale:** Downed crew cannot RUN. They can only escape if other crew CARRY them. Each CARRY action from a standing crewmate advances the downed crewmate's track by 1, but requires 2 standing crew to contribute (so 2 CARRY actions = downed crewmate moves +1).

### Finale Math (example, 12 surviving crew, 2 downed)

- 10 standing crew, 2 downed
- Each standing crew needs 3 RUNs to escape (3 rounds × 1 RUN = track 3)
- Downed crew need 2 × 3 = 6 CARRY actions total to escape (2 carries per round × 3 rounds)
- 10 standing crew have 30 action slots over 3 rounds
- Escaping themselves: 10 × 3 = 30 actions → exactly enough, but then no one helps the downed
- Tension: do you leave the 2 downed, or sacrifice some of your own RUNs to CARRY them?

### Win / Loss

**Survival phase loss:**
- Reactor hits 0 → instant meltdown, game over
- All crew downed → game over

**Finale outcomes:**
- **Win:** All surviving crew reach escape track 3 before collapse hits 100%
- **Partial win:** Some crew reach the pods, some don't (app reports "X of Y survived")
- **Loss:** Collapse hits 100% before anyone reaches the pods → total loss

**The arc:** Endure → Escape. Two-phase victory. Clock pressure in both phases (rounds ticking in phase 1, collapse bar in phase 2).

---

## Station Systems

The station has 6 systems, each with health (0-100):

| System | Function | If it hits 0 |
|--------|----------|--------------|
| Reactor | Powers everything | Core meltdown — instant loss |
| Life Support | Generates O2, keeps crew alive | Crew suffocate within 3 rounds |
| Med Bay | Heals crew, revives downed | Revive actions no longer possible |
| Hull | Holds the station together | Player slots lost — fewer actions/round |
| Comms | Calls rescue / sends distress | Comms dark — finale objective stalls |
| Shields | Protects from external threats | All systems degrade +2/round |

---

## Crises

### Crisis Data Model

```
Crisis {
  id: string
  name: string           // "Coolant Leak"
  description: string    // 1-line flavor: "Coolant spraying from reactor coupling"
  system: System         // which system it drains
  drainRate: int         // health lost per round if unresolved
  crewRequired: int      // 1, 2, or 3 players needed to FIX
  tier: int              // 1 (early), 2 (mid), 3 (late)
  weight: int            // spawn probability weight
}
```

### Crisis Tiers (gated by round)

| Tier | Rounds | Drain rate | Crew to FIX | Pool size |
|------|--------|-----------|-------------|-----------|
| 1 | 1-3 | -2 to -4 | 1-2 | ~15 crises |
| 2 | 4-7 | -3 to -6 | 2 | ~15 crises |
| 3 | 8-10 | -5 to -10 | 2-3 | ~10 crises |

**Total pool:** ~40 crises to launch.

### Flavor Variety

Each crisis has multiple name/description variants so repeats feel fresh:
- "Coolant Leak" / "Coolant Line Rupture" / "Primary Coolant Failure"
- Same mechanical effect, different text. Cheap replayability.

### Spawn Logic (per round)

1. Determine crisis count: 1 (rounds 1-3) → 2 (rounds 4-7) → 3 (rounds 8-10)
2. Filter pool by valid tier for current round.
3. Weighted random selection.
4. No two crises target the same system in the same round (prevents "all 3 crises hit hull").
5. Ensure at least one crisis requires crewRequired >= 2 (forces coordination).

### Escalation Curve

- Rounds 1-3: 1 crisis/round, mild drain (-2 to -4)
- Rounds 4-7: 2 crises/round, moderate drain (-3 to -6)
- Rounds 8-10: 3 crises/round, severe drain (-5 to -10)

---

## Player Actions

Each round, every player picks exactly ONE action. Options update based on current crises.

### Survival Phase Actions

| Action | Effect | Requirement |
|--------|--------|-------------|
| FIX a crisis | Stops the drain on that system | Crew requirement varies by crisis (1, 2, or 3) |
| BOLSTER a system | +5 to a system's health | 1 player, always available |
| REVIVE a downed crewmate | Brings a KO'd player back into action | 1 player, requires Med Bay > 0 |

### Crew Power Mechanic

- Crises are tagged with a crew requirement: e.g. `FIX requires 2 crew`.
- If fewer than the required players try to FIX the same crisis, nothing happens — wasted actions.
- If enough players FIX the same crisis, it's resolved — drain stops.
- Players see the requirement when choosing, enabling coordination: "Someone help me on the reactor!"
- This is the core social/co-op mechanic — the app forces players to talk.

### Downed Crew

- If Life Support hits 0, a crew member gets KO'd each round (random, app picks).
- KO'd players can't act — their screen shows "YOU ARE DOWN. Waiting for revive."
- Revive requires 1 player + Med Bay > 0.
- If all crew downed → loss.

### Finale Phase Actions

| Action | Effect | Requirement |
|--------|--------|-------------|
| RUN | Advance your own escape track by +1 | 1 player |
| CARRY | Advance a downed crewmate's escape track by +1 | 2 standing players must both CARRY the same downed crewmate |
| HOLD | Seal bulkhead, reduce collapse bar by ~15% | 1 player |

### Finale Win Condition

- Each crew member's escape track must reach 3 to be safe.
- Collapse bar must stay below 100% until all escaping crew reach track 3.
- Collapse starts at 0, fills +33% per round → hits ~99% at end of round 3 without any HOLD.
- 2 HOLDs per round reduce collapse by 30% → keeps it survivable through round 3.
- This creates the core finale tension: every HOLD is a crewmate not running for the pods.

---

## Tech Architecture

### Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend | FastAPI (Python) | Async, native WebSocket support, matches existing Python skills |
| Frontend | SvelteKit (SPA, adapter-static) | Lightweight, small bundle for phones, minimal boilerplate |
| Realtime | WebSocket | Server pushes state changes; clients send actions. Synchronized updates to 15 clients. |
| State | In-memory dict per game | No DB needed. Games last 20 min. No persistence required. |
| Deployment | Single Docker container, single port | One command to run. Matches existing deployment pattern. |

### State Authority

- Server is the single source of truth. Clients are "dumb" — they render what the server sends.
- Client sends action → server validates → server recomputes → server broadcasts new state to all players in that room.
- No client-side game logic. Prevents cheating, keeps logic in one place.

### Architecture Diagram

```
SvelteKit SPA            FastAPI server (one uvicorn process)
  - Join screen              - WebSocket /ws/{room_code}
  - Lobby                    - Game engine (in-memory)
  - Play screen (action)     - tick() loop per game
  - Finale screen            - broadcasts state to all clients
  - Results screen
        |
        v
   WebSocket
   - send: { action: "FIX", target: "reactor" }
   - recv: { phase, systems, crises, round, clock, crew }
```

### Screens (5 total)

1. **Join** — enter room code + name
2. **Lobby** — see who's joined, host clicks Start
3. **Play** — station status + action picker + countdown
4. **Finale** — escape sequence UI (RUN / CARRY / HOLD)
5. **Results** — win/loss + crew survival report

---

## Deployment (Docker)

### Single Container, Single Port

```
Docker container (one process: uvicorn)
├── FastAPI
│   ├── WebSocket /ws/{room_code}  (game logic)
│   └── StaticFiles                  (serves SPA build)
└── SvelteKit SPA build (static HTML/JS/CSS)
```

- SvelteKit uses `adapter-static` → builds to a folder of static files (no Node server needed at runtime).
- FastAPI serves those static files + handles WebSocket.
- One `uvicorn` process does everything.
- One port (e.g. 8000). Players hit `http://your-host:8000`, get the SPA, then connect WS to the same host.

### Dockerfile (multi-stage)

```dockerfile
# Stage 1: Build SvelteKit SPA
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/ .
RUN npm install && npm run build

# Stage 2: Python backend + serve static
FROM python:3.12-slim
WORKDIR /app
COPY backend/ .
COPY --from=frontend /app/frontend/build ./static
RUN pip install -r requirements.txt
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Project Structure

```
fun-session/
├── Dockerfile
├── backend/
│   ├── main.py              (FastAPI app, routes, WS handler)
│   ├── game.py              (Game class — state, tick, resolve)
│   ├── crises.py            (crisis pool, spawn logic)
│   └── requirements.txt     (fastapi, uvicorn, websockets)
└── frontend/
    ├── package.json
    ├── svelte.config.js     (adapter-static, SPA mode)
    ├── src/
    │   ├── routes/
    │   │   ├── +page.svelte         (join screen)
    │   │   ├── lobby/+page.svelte
    │   │   ├── play/+page.svelte
    │   │   ├── finale/+page.svelte
    │   │   └── results/+page.svelte
    │   ├── lib/
    │   │   ├── websocket.ts         (WS client + reconnect)
    │   │   ├── stores.ts            (reactive game state)
    │   │   └── types.ts             (shared TS types matching backend)
    │   └── app.html
    └── static/
```

### Run

```bash
docker build -t station-meltdown .
docker run -p 8000:8000 station-meltdown
# Players go to http://<your-ip>:8000
```

### Dev Workflow

- Backend: `uvicorn main:app --reload` in `backend/`
- Frontend: `npm run dev` in `frontend/` (Vite dev server proxies WS to backend)
- Prod: `docker build && docker run`

---

## Out of Scope (MVP)

These are intentionally excluded from the initial build. Can be added later based on playtesting:

- **Items / inventory** — dropped to keep action set simple (3 actions only).
- **PREP action (bank tokens)** — dropped to reduce phone UI complexity.
- **Player roles / abilities** — not in MVP. Could be added as expansion if vanilla feels samey.
- **SCAN action (reveal next round early)** — potential 4th action if late-game feels one-note.
- **Session history / stats persistence** — no DB. Games are ephemeral.
- **Multiple themes / settings** — sci-fi only for launch. Rotating themes is a future expansion.
- **Spectator mode** — not needed for 15-player cap.
- **Audio / music** — out of scope. Visual countdown and state changes are sufficient.

---

## Open Questions for Implementation

These don't change the design but will need answers during implementation:

1. **Tie-breaking in finale:** If collapse bar hits exactly 100% on the same round the last crew escapes, win or loss? (Recommend: win — escaping on the final tick counts.)
2. **AFK handling:** If a player doesn't submit an action in 45 sec, what happens? (Recommend: their action defaults to BOLSTER on the lowest-health system. No penalty, but no strategic choice either.)
3. **Player disconnect mid-game:** How to handle? (Recommend: treat as downed — they stop contributing but aren't fully removed. If they reconnect, they're back in.)
4. **Minimum player count:** Game supports up to 15. What's the minimum for a viable game? (Recommend: 4 — enough to crew-power a 2-player FIX crisis.)