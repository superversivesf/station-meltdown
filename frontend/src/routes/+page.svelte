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
      } else if ($connectionStatus === 'disconnected') {
        // Server unreachable — stop polling so the interval can't leak.
        clearInterval(checkConnected);
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
    margin: 4rem auto;
    padding: 2rem 1.5rem;
    background: var(--station-panel);
    border: 1px solid var(--station-border);
    border-radius: 6px;
    box-shadow:
      0 0 40px rgba(59, 130, 246, 0.08),
      inset 0 1px 0 rgba(255,255,255,0.04);
    position: relative;
  }
  .container::before {
    content: 'EMERGENCY PROTOCOL';
    position: absolute;
    top: -10px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--warn-amber);
    color: #0a0e14;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.15em;
    padding: 0.15rem 0.75rem;
    border-radius: 2px;
  }
  h1 {
    font-size: 1.9rem;
    margin: 0.5rem 0;
    letter-spacing: 0.05em;
    text-align: center;
    text-shadow: 0 0 20px rgba(239, 68, 68, 0.3);
  }
  .tagline {
    color: var(--text-muted);
    font-size: 0.88rem;
    margin-bottom: 2rem;
    text-align: center;
    line-height: 1.5;
  }
  .form { display: flex; flex-direction: column; gap: 1.25rem; }
  label {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    font-size: 0.78rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  input {
    padding: 0.85rem 1rem;
    font-size: 1rem;
    background: #0a0e14;
    color: var(--text-primary);
    border: 1px solid var(--station-border);
    border-radius: 4px;
    transition: border-color 0.2s, box-shadow 0.2s;
  }
  input:focus {
    outline: none;
    border-color: var(--action-blue);
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }
  input::placeholder { color: var(--text-dim); }
  button {
    padding: 0.85rem;
    font-size: 1rem;
    font-weight: 600;
    background: linear-gradient(180deg, #4f6b8a 0%, #2d3e54 100%);
    color: var(--text-primary);
    border: 1px solid #3a5070;
    border-radius: 4px;
    cursor: pointer;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    transition: background 0.2s, box-shadow 0.2s;
  }
  button:hover {
    background: linear-gradient(180deg, #5a7a9e 0%, #354866 100%);
    box-shadow: 0 0 16px rgba(59, 130, 246, 0.3);
  }
  .error {
    color: var(--warn-red);
    font-size: 0.85rem;
    text-align: center;
    padding: 0.5rem;
    background: rgba(239, 68, 68, 0.08);
    border-left: 3px solid var(--warn-red);
    border-radius: 2px;
  }
  .status {
    color: var(--text-dim);
    font-size: 0.75rem;
    margin-top: 1.5rem;
    text-align: center;
    font-family: 'Consolas', monospace;
  }
</style>