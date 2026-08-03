<script lang="ts">
  import { gameState, isHost, connectionStatus } from '$lib/stores';

  function startGame() {
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