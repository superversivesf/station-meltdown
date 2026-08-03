<script lang="ts">
  import { goto } from '$app/navigation';
  import { GameWebSocket } from '$lib/websocket';
  import { handleMessage, gameState, connectionStatus, setWs } from '$lib/stores';

  let roomCode = $state('');
  let name = $state('');
  let localError = $state('');

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
    const ws = new GameWebSocket(roomCode.toUpperCase());
    setWs(ws);
    ws.onMessage(handleMessage);
    ws.onStatusChange((status) => connectionStatus.set(status));
    ws.connect();
    const checkConnected = setInterval(() => {
      if ($connectionStatus === 'connected') {
        clearInterval(checkConnected);
        ws.join(name.trim());
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