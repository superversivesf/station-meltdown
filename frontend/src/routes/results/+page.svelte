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