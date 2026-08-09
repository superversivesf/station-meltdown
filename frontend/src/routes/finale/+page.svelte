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
            {#if $gameState.players.filter(p => !p.is_down && p.escape_track < 3).length >= 2 && $gameState.players.some(p => p.is_down && p.escape_track < 3)}
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
    max-width: 520px;
    margin: 0 auto;
    padding: 1rem 0.75rem;
  }
  header {
    text-align: center;
    padding: 0.75rem 1rem;
    background: var(--station-panel);
    border: 1px solid #4a1a1a;
    border-radius: 6px;
    margin-bottom: 1.25rem;
  }
  h1 {
    font-size: 1.1rem;
    margin: 0;
    letter-spacing: 0.08em;
    color: var(--warn-red);
    text-shadow: 0 0 16px rgba(239, 68, 68, 0.3);
  }
  section { margin: 1.25rem 0; }
  h2 {
    font-size: 0.72rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin-bottom: 0.6rem;
  }

  /* Collapse bar */
  .collapse-bar {
    height: 24px;
    background: #0a0e14;
    border: 1px solid #3d1a1a;
    border-radius: 4px;
    overflow: hidden;
    position: relative;
  }
  .collapse-fill {
    height: 100%;
    background: linear-gradient(90deg, #b45309 0%, #ef4444 70%, #dc2626 100%);
    transition: width 0.4s ease;
    box-shadow: 0 0 12px rgba(239, 68, 68, 0.4);
  }
  .collapse-pct {
    font-weight: 700;
    font-size: 0.9rem;
    font-family: 'Consolas', monospace;
    color: var(--warn-red);
  }

  /* Crew escape progress */
  .crew-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.4rem 0;
    font-size: 0.85rem;
  }
  .crew-row.down .crew-name { color: var(--warn-red); }
  .crew-row.safe .crew-name { color: var(--ok-green); }
  .crew-name { flex: 0 0 110px; }
  .tag {
    font-size: 0.6rem;
    padding: 0.1rem 0.35rem;
    background: var(--warn-red);
    color: #0a0e14;
    border-radius: 2px;
    font-weight: 700;
    letter-spacing: 0.06em;
  }
  .tag.safe { background: var(--ok-green); }
  .escape-bar {
    flex: 1;
    height: 12px;
    background: #0a0e14;
    border: 1px solid var(--station-border);
    border-radius: 4px;
    overflow: hidden;
  }
  .escape-fill {
    height: 100%;
    background: linear-gradient(90deg, #16a34a 0%, #4ade80 100%);
    transition: width 0.4s ease;
    box-shadow: 0 0 6px rgba(74, 222, 128, 0.3);
  }
  .track {
    flex: 0 0 36px;
    text-align: right;
    font-family: 'Consolas', monospace;
    color: var(--text-muted);
  }

  /* Action buttons */
  .action-buttons {
    display: flex;
    gap: 0.6rem;
  }
  .action-btn {
    flex: 1;
    padding: 1.1rem 0.5rem;
    font-size: 0.9rem;
    font-weight: 700;
    border: 1px solid;
    border-radius: 4px;
    cursor: pointer;
    text-align: center;
    letter-spacing: 0.06em;
    transition: background 0.15s, box-shadow 0.15s;
  }
  .action-btn small {
    font-weight: 400;
    font-size: 0.68rem;
    display: block;
    margin-top: 0.25rem;
    opacity: 0.8;
  }
  .action-btn.run {
    border-color: #2a5a35;
    background: rgba(74, 222, 128, 0.06);
    color: var(--ok-green);
  }
  .action-btn.run:hover {
    background: rgba(74, 222, 128, 0.12);
    box-shadow: 0 0 12px rgba(74, 222, 128, 0.2);
  }
  .action-btn.carry {
    border-color: #3d3060;
    background: rgba(167, 139, 250, 0.06);
    color: var(--purple-accent);
  }
  .action-btn.carry:hover {
    background: rgba(167, 139, 250, 0.12);
  }
  .action-btn.hold {
    border-color: #4a3010;
    background: rgba(245, 158, 11, 0.06);
    color: var(--warn-amber);
  }
  .action-btn.hold:hover {
    background: rgba(245, 158, 11, 0.12);
  }
  .confirm {
    padding: 1.25rem;
    background: var(--station-panel);
    border: 1px solid var(--station-border);
    border-radius: 4px;
    text-align: center;
  }
  .confirm p { margin-bottom: 1rem; color: var(--text-primary); }
  button.submit {
    background: linear-gradient(180deg, #4f6b8a 0%, #2d3e54 100%);
    border-color: #3a5070;
    color: #fff;
  }
  button { margin: 0.25rem; }

  .downed, .safe { text-align: center; padding: 3rem 1rem; }
  .downed h1 {
    color: var(--warn-red);
    font-size: 1.8rem;
    letter-spacing: 0.1em;
    text-shadow: 0 0 20px rgba(239, 68, 68, 0.4);
    margin-bottom: 1rem;
  }
  .downed p { color: var(--text-muted); }
  .safe h1 {
    color: var(--ok-green);
    font-size: 1.6rem;
    letter-spacing: 0.08em;
    text-shadow: 0 0 16px rgba(74, 222, 128, 0.3);
    margin-bottom: 0.5rem;
  }
  .safe p { color: var(--text-muted); }
</style>