<script lang="ts">
  import { gameState, myPlayer, errorMessage } from '$lib/stores';
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
    selectedAction = null;
    selectedSystem = null;
    selectedCrisisId = null;
    selectedPlayerId = null;
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