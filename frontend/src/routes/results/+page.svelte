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
    max-width: 520px;
    margin: 2rem auto;
    padding: 1.5rem 1.25rem;
    text-align: center;
  }
  .result {
    padding: 2.5rem 1.5rem;
    border-radius: 6px;
    margin-bottom: 1.75rem;
    border: 1px solid;
  }
  .victory {
    background: rgba(74, 222, 128, 0.06);
    border-color: #2a5a35;
    box-shadow: 0 0 40px rgba(74, 222, 128, 0.08);
  }
  .partial {
    background: rgba(245, 158, 11, 0.06);
    border-color: #4a3010;
    box-shadow: 0 0 40px rgba(245, 158, 11, 0.08);
  }
  .loss {
    background: rgba(239, 68, 68, 0.06);
    border-color: #4a1a1a;
    box-shadow: 0 0 40px rgba(239, 68, 68, 0.08);
  }
  h1 {
    font-size: 1.8rem;
    margin-bottom: 0.5rem;
    letter-spacing: 0.08em;
  }
  .victory h1 {
    color: var(--ok-green);
    text-shadow: 0 0 20px rgba(74, 222, 128, 0.3);
  }
  .partial h1 {
    color: var(--warn-amber);
    text-shadow: 0 0 20px rgba(245, 158, 11, 0.3);
  }
  .loss h1 {
    color: var(--warn-red);
    text-shadow: 0 0 20px rgba(239, 68, 68, 0.3);
  }
  .result p {
    color: var(--text-muted);
    font-size: 0.95rem;
    margin-top: 0.75rem;
  }
  .crew-report {
    text-align: left;
    margin: 1.75rem 0;
    background: var(--station-panel);
    border: 1px solid var(--station-border);
    border-radius: 6px;
    padding: 1.25rem;
  }
  h2 {
    font-size: 0.78rem;
    margin-bottom: 1rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    text-align: center;
  }
  h3 {
    font-size: 0.85rem;
    margin-bottom: 0.5rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid var(--station-border);
    letter-spacing: 0.04em;
  }
  .survived h3 { color: var(--ok-green); }
  .lost h3 { color: var(--warn-red); }
  ul { list-style: none; padding: 0; margin: 0 0 1.25rem; }
  li {
    padding: 0.55rem 0.75rem;
    border-bottom: 1px solid var(--station-border);
    font-size: 0.95rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  li::before {
    content: '\25B8';
    font-size: 0.7rem;
    color: var(--text-dim);
  }
  .survivor { color: var(--ok-green); }
  .survivor::before { color: var(--ok-green); }
  .casualty { color: var(--warn-red); }
  .casualty::before { color: var(--warn-red); }
  .empty { color: var(--text-dim); font-style: italic; }
  .empty::before { content: '\2205'; }
  button {
    padding: 0.85rem 2.5rem;
    font-size: 0.95rem;
    font-weight: 600;
    background: linear-gradient(180deg, #4f6b8a 0%, #2d3e54 100%);
    color: var(--text-primary);
    border: 1px solid #3a5070;
    border-radius: 4px;
    cursor: pointer;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    transition: background 0.2s, box-shadow 0.2s;
  }
  button:hover {
    background: linear-gradient(180deg, #5a7a9e 0%, #354866 100%);
    box-shadow: 0 0 16px rgba(59, 130, 246, 0.3);
  }
</style>