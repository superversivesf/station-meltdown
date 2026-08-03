import { writable, derived } from 'svelte/store';
import type { GameState, ServerMessage } from './types';

export const gameState = writable<GameState | null>(null);
export const playerId = writable<string | null>(null);
export const connectionStatus = writable<'connecting' | 'connected' | 'disconnected' | 'reconnecting'>('connecting');
export const errorMessage = writable<string | null>(null);

export function handleMessage(msg: ServerMessage) {
  switch (msg.type) {
    case 'state':
      gameState.set(msg.state);
      playerId.set(msg.player_id);
      errorMessage.set(null);
      break;
    case 'action_ack':
      // Action acknowledged — could show a brief confirmation
      break;
    case 'error':
      errorMessage.set(msg.message);
      break;
  }
}

export const currentPhase = derived(gameState, ($gs) => $gs?.phase ?? null);
export const isHost = derived(
  [gameState, playerId],
  ([$gs, $pid]) => $gs?.players.find((p) => p.id === $pid)?.is_host ?? false
);
export const myPlayer = derived(
  [gameState, playerId],
  ([$gs, $pid]) => $gs?.players.find((p) => p.id === $pid) ?? null
);