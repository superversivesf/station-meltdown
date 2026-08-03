<script lang="ts">
  import { gameState, isHost, connectionStatus } from '$lib/stores';

  function startGame() {
    const event = new CustomEvent('start-game');
    window.dispatchEvent(event);
  }
</script>

<div class="container">
  <h1>Lobby — Room <span class="code">{$gameState?.room_code ?? '...'}</span></h1>

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
    max-width: 480px;
    margin: 3rem auto;
    padding: 1.75rem 1.5rem;
    background: var(--station-panel);
    border: 1px solid var(--station-border);
    border-radius: 6px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04);
  }
  h1 {
    font-size: 1.4rem;
    margin-bottom: 1.5rem;
    letter-spacing: 0.04em;
  }
  h1 .code {
    color: var(--warn-amber);
    font-family: 'Consolas', monospace;
    font-weight: 700;
  }
  .players {
    margin: 1.5rem 0;
    border-top: 1px solid var(--station-border);
    padding-top: 1rem;
  }
  h2 {
    font-size: 0.78rem;
    margin-bottom: 0.75rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.12em;
  }
  ul { list-style: none; padding: 0; margin: 0; }
  li {
    padding: 0.65rem 0.85rem;
    border-bottom: 1px solid var(--station-border);
    font-size: 0.95rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  li:last-child { border-bottom: none; }
  li::before {
    content: '\25B8';
    color: var(--text-dim);
    font-size: 0.7rem;
  }
  li.host { color: var(--text-primary); font-weight: 600; }
  li.host::before { color: var(--warn-amber); }
  .badge {
    font-size: 0.65rem;
    background: var(--warn-amber);
    color: #0a0e14;
    padding: 0.12rem 0.45rem;
    border-radius: 2px;
    font-weight: 700;
    letter-spacing: 0.08em;
  }
  button {
    width: 100%;
    padding: 0.95rem;
    font-size: 0.95rem;
    font-weight: 600;
    background: linear-gradient(180deg, #3a7d4f 0%, #1f5a35 100%);
    color: var(--text-primary);
    border: 1px solid #4a8a5e;
    border-radius: 4px;
    cursor: pointer;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    transition: background 0.2s, box-shadow 0.2s;
  }
  button:hover:not(:disabled) {
    background: linear-gradient(180deg, #459260 0%, #266b40 100%);
    box-shadow: 0 0 16px rgba(74, 222, 128, 0.25);
  }
  button:disabled {
    background: #1a1e26;
    border-color: var(--station-border);
    color: var(--text-dim);
    cursor: not-allowed;
  }
  .warning {
    color: var(--warn-amber);
    text-align: center;
    padding: 0.75rem;
    background: rgba(245, 158, 11, 0.06);
    border: 1px solid rgba(245, 158, 11, 0.2);
    border-radius: 4px;
    font-size: 0.85rem;
  }
  .waiting {
    color: var(--text-muted);
    font-style: italic;
    text-align: center;
    padding: 0.75rem;
  }
  .status {
    color: var(--text-dim);
    font-size: 0.72rem;
    margin-top: 1.5rem;
    text-align: center;
    font-family: 'Consolas', monospace;
  }
</style>