<script lang="ts">
  import { gameState, myPlayer, errorMessage, connectionStatus } from '$lib/stores';
  import type { SystemName, ActionType, Crisis } from '$lib/types';

  let selectedAction = $state<ActionType | null>(null);
  let selectedSystem = $state<SystemName | null>(null);
  let selectedCrisisId = $state<string | null>(null);
  let selectedPlayerId = $state<string | null>(null);

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

  let timeLeft = $state(0);

  $effect(() => {
    const deadline = $gameState?.action_phase_deadline;
    if (!deadline) {
      timeLeft = 0;
      return;
    }
    const update = () => {
      timeLeft = Math.max(0, Math.ceil(deadline - Date.now() / 1000));
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  });

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
    // Keep the selection until the server acks (or errors) — a state
    // broadcast arriving between submit and ack must not wipe the pick.
    // The ack/error arrives via the store; see the $effect below.
    submitted = true;
  }

  // Clear the selection once the server has accepted the action (it shows
  // up in pending_actions) or rejected it with an error. Until then,
  // incoming state broadcasts leave the picker untouched.
  let submitted = $state(false);
  $effect(() => {
    if (!submitted) return;
    // Bail if disconnected — the action will never be acked.
    if ($connectionStatus === 'disconnected') {
      submitted = false;
      return;
    }
    if ($errorMessage) {
      submitted = false;
      selectedAction = null;
      selectedSystem = null;
      selectedCrisisId = null;
      selectedPlayerId = null;
      return;
    }
    const accepted = $gameState?.pending_actions.some(
      (a) => a.player_id === $myPlayer?.id
    );
    if (accepted) {
      submitted = false;
      selectedAction = null;
      selectedSystem = null;
      selectedCrisisId = null;
      selectedPlayerId = null;
    }
  });

  function cancelAction() {
    submitted = false;
    selectedAction = null;
    selectedSystem = null;
    selectedCrisisId = null;
    selectedPlayerId = null;
  }

  // If the chosen crisis disappears (resolved server-side), drop the stale
  // selection instead of rendering a blank confirm panel.
  $effect(() => {
    if (selectedAction === 'fix' && selectedCrisisId) {
      const stillThere = $gameState?.active_crises.some((c) => c.id === selectedCrisisId);
      if (stillThere === false) {
        selectedAction = null;
        selectedCrisisId = null;
        selectedSystem = null;
      }
    }
  });
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
          <button onclick={cancelAction}>Cancel</button>
        </div>
      {:else if selectedAction === 'bolster'}
        <div class="selected-action">
          <p>BOLSTERing: {systemLabels[selectedSystem as SystemName]}</p>
          <button onclick={submitAction} class="submit">Confirm BOLSTER</button>
          <button onclick={cancelAction}>Cancel</button>
        </div>
      {:else if selectedAction === 'revive'}
        <div class="selected-action">
          <p>REVIVEing crewmate</p>
          <button onclick={submitAction} class="submit">Confirm REVIVE</button>
          <button onclick={cancelAction}>Cancel</button>
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
    max-width: 520px;
    margin: 0 auto;
    padding: 1rem 0.75rem;
  }

  /* Header bar */
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.75rem 1rem;
    background: var(--station-panel);
    border: 1px solid var(--station-border);
    border-radius: 6px;
    margin-bottom: 1rem;
  }
  h1 {
    font-size: 1rem;
    margin: 0;
    letter-spacing: 0.06em;
    color: var(--text-primary);
  }
  .timer {
    font-size: 1.6rem;
    font-weight: 700;
    font-family: 'Consolas', 'Courier New', monospace;
    padding: 0.25rem 0.85rem;
    background: #0a0e14;
    color: var(--ok-green);
    border-radius: 4px;
    border: 1px solid #1a3328;
    min-width: 80px;
    text-align: center;
  }
  .timer.urgent {
    color: var(--warn-red);
    border-color: #4a1a1a;
    animation: pulse 1s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  /* Station systems grid */
  section { margin: 1.25rem 0; }
  h2 {
    font-size: 0.72rem;
    margin-bottom: 0.6rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.14em;
  }
  .system-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.6rem;
  }
  .system {
    border-left: 3px solid;
    padding: 0.6rem 0.75rem;
    background: var(--station-panel);
    border-radius: 3px;
    border-top: 1px solid var(--station-border);
    border-right: 1px solid var(--station-border);
    border-bottom: 1px solid var(--station-border);
  }
  .sys-name {
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.04em;
  }
  .health-bar {
    height: 6px;
    background: #0a0e14;
    border-radius: 3px;
    margin: 0.4rem 0 0.25rem;
    overflow: hidden;
    border: 1px solid var(--station-border);
  }
  .health-fill {
    height: 100%;
    transition: width 0.4s ease;
    box-shadow: 0 0 6px currentColor;
  }
  .health-num {
    font-size: 0.7rem;
    color: var(--text-dim);
    font-family: 'Consolas', monospace;
  }

  /* Crisis cards */
  .crisis {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.85rem 1rem;
    border: 1px solid #4a3010;
    border-left: 3px solid var(--warn-amber);
    border-radius: 4px;
    margin-bottom: 0.6rem;
    background: linear-gradient(180deg, rgba(245, 158, 11, 0.06) 0%, rgba(245, 158, 11, 0.02) 100%);
  }
  .crisis.selected {
    border-color: var(--action-blue);
    border-left-color: var(--action-blue);
    background: rgba(59, 130, 246, 0.08);
    box-shadow: 0 0 12px rgba(59, 130, 246, 0.15);
  }
  .crisis-info { flex: 1; }
  .crisis-info strong {
    font-size: 0.88rem;
    color: var(--warn-amber);
  }
  .crisis-info p {
    font-size: 0.78rem;
    color: var(--text-muted);
    margin: 0.2rem 0 0.35rem;
  }
  .drain {
    color: var(--warn-red);
    font-size: 0.72rem;
    font-weight: 700;
    font-family: 'Consolas', monospace;
  }
  .crew {
    color: var(--purple-accent);
    font-size: 0.72rem;
    margin-left: 0.6rem;
  }

  /* Buttons */
  button {
    padding: 0.5rem 1rem;
    font-size: 0.82rem;
    font-weight: 600;
    border: 1px solid var(--station-border);
    background: #1a212e;
    color: var(--text-primary);
    border-radius: 4px;
    cursor: pointer;
    letter-spacing: 0.05em;
    transition: background 0.15s, border-color 0.15s;
  }
  button:hover { background: #242d3d; }
  button.active {
    border-color: var(--action-blue);
    background: rgba(59, 130, 246, 0.15);
  }
  button.submit {
    background: linear-gradient(180deg, #4f6b8a 0%, #2d3e54 100%);
    border-color: #3a5070;
    color: #fff;
  }
  button.submit:hover {
    background: linear-gradient(180deg, #5a7a9e 0%, #354866 100%);
  }

  .action-options { display: flex; flex-direction: column; gap: 1rem; }
  .bolster-options p, .revive-options p {
    font-size: 0.82rem;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
  }
  .bolster-options {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .bolster-options > p { width: 100%; }
  .bolster-options button {
    border-left-width: 3px;
  }
  .revive-options button {
    color: var(--purple-accent);
    border-color: #3d3060;
  }

  .selected-action {
    padding: 1.25rem;
    background: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.3);
    border-radius: 4px;
    text-align: center;
  }
  .selected-action p {
    margin-bottom: 1rem;
    color: var(--text-primary);
  }

  .downed {
    text-align: center;
    padding: 4rem 1rem;
  }
  .downed h1 {
    color: var(--warn-red);
    font-size: 1.8rem;
    letter-spacing: 0.1em;
    text-shadow: 0 0 20px rgba(239, 68, 68, 0.4);
    margin-bottom: 1rem;
  }
  .downed p { color: var(--text-muted); }
  .error {
    color: var(--warn-red);
    text-align: center;
    padding: 0.6rem;
    background: rgba(239, 68, 68, 0.06);
    border-left: 3px solid var(--warn-red);
    border-radius: 2px;
  }
</style>