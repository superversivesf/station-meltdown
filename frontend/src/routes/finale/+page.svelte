<script lang="ts">
  import { gameState, myPlayer } from '$lib/stores';
  import type { Player } from '$lib/types';

  let selectedAction = $state<'run' | 'carry' | 'hold' | null>(null);
  let carryTargetId = $state<string | null>(null);

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