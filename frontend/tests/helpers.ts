import { spawn, type ChildProcess } from 'child_process';
import { WebSocket } from 'ws';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const BACKEND_PORT = process.env.E2E_BACKEND_PORT || '8090';
const BACKEND_HOST = '127.0.0.1';
const BASE_WS = `ws://${BACKEND_HOST}:${BACKEND_PORT}/ws`;

// Backend is started by Playwright's webServer config — we just wait for it
export async function waitForBackend(): Promise<void> {
  const maxAttempts = 30;
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const resp = await fetch(`http://${BACKEND_HOST}:${BACKEND_PORT}/api/health`);
      if (resp.ok) return;
    } catch {
      // not ready
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error('backend not ready after 15s');
}

export function getBaseUrl() {
  return BASE_WS;
}

export function getBackendUrl() {
  return `http://${BACKEND_HOST}:${BACKEND_PORT}`;
}

export interface ClientState {
  phase: string;
  round_number: number;
  systems: Record<string, number>;
  players: Array<{ id: string; name: string; is_host: boolean; is_down: boolean; escape_track: number }>;
  active_crises: Array<{ id: string; name: string; system: string; drain_rate: number; crew_required: number }>;
  collapse_bar: number;
  victory: boolean;
  partial: boolean;
  crew_survived: string[];
  crew_lost: string[];
  action_phase_deadline: number | null;
}

export class WsClient {
  private ws: WebSocket;
  private messages: any[] = [];
  public playerId: string | null = null;
  public lastState: ClientState | null = null;
  public lastError: string | null = null;

  constructor(roomCode: string) {
    this.ws = new WebSocket(`${BASE_WS}/${roomCode}`);
  }

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('ws connect timeout')), 10000);
      this.ws.on('open', () => {
        clearTimeout(timeout);
        resolve();
      });
      this.ws.on('error', (err) => {
        clearTimeout(timeout);
        reject(err);
      });
      this.ws.on('message', (data) => {
        const msg = JSON.parse(data.toString());
        this.messages.push(msg);
        if (msg.type === 'state') {
          this.playerId = msg.player_id;
          this.lastState = msg.state;
        } else if (msg.type === 'error') {
          this.lastError = msg.message;
          console.log(`WS Error [${this.playerId}]: ${msg.message}`);
        }
      });
    });
  }

  send(msg: any) {
    this.ws.send(JSON.stringify(msg));
  }

  join(name: string) {
    this.send({ type: 'join', name });
  }

  start() {
    this.send({ type: 'start' });
  }

  resolve() {
    this.send({ type: 'resolve' });
  }

  action(actionType: string, extra: any = {}) {
    this.send({ type: 'action', action_type: actionType, ...extra });
  }

  debugSetSystem(system: string, hp: number) {
    this.send({ type: 'debug_set_system', system, hp });
  }

  debugDownPlayer(name: string) {
    this.send({ type: 'debug_down_player', name });
  }

  waitForState(predicate: (s: ClientState) => boolean, timeoutMs = 15000): Promise<ClientState> {
    return new Promise((resolve, reject) => {
      if (this.lastState && predicate(this.lastState)) {
        resolve(this.lastState);
        return;
      }
      const timeout = setTimeout(() => {
        reject(new Error(`state predicate timeout; last phase=${this.lastState?.phase}, round=${this.lastState?.round_number}`));
      }, timeoutMs);
      const interval = setInterval(() => {
        if (this.lastState && predicate(this.lastState)) {
          clearTimeout(timeout);
          clearInterval(interval);
          resolve(this.lastState);
        }
      }, 100);
    });
  }

  async waitForPhase(phase: string, timeoutMs = 30000): Promise<ClientState> {
    return this.waitForState((s) => s.phase === phase, timeoutMs);
  }

  close() {
    this.ws.close();
  }
}

export async function createClient(roomCode: string, name: string): Promise<WsClient> {
  const client = new WsClient(roomCode);
  await client.connect();
  client.join(name);
  await client.waitForState((s) => s.players.some((p) => p.name === name));
  return client;
}

export async function setupGame(roomCode: string, playerNames: string[]): Promise<WsClient[]> {
  const clients: WsClient[] = [];
  for (const name of playerNames) {
    const client = await createClient(roomCode, name);
    clients.push(client);
  }
  // Verify the first client is the host
  if (clients[0].lastState && clients[0].lastState.players.length > 0) {
    const hostPlayer = clients[0].lastState.players[0];
    if (!hostPlayer.is_host) {
      throw new Error(`Expected first player ${hostPlayer.name} to be host`);
    }
  }
  return clients;
}

export async function playSurvivalRound(
  clients: WsClient[],
  strategy: 'fix-all' | 'fix-insufficient' | 'no-fix' = 'fix-all'
) {
  // Each client reads the current crises and picks an action
  const state = clients[0].lastState!;
  const crises = state.active_crises;

  if (strategy === 'fix-insufficient' && crises.length > 0) {
    // Only first player tries to FIX (insufficient for crew_required >= 2)
    const crisis = crises[0];
    if (crisis.crew_required >= 2) {
      clients[0].action('fix', { target_system: crisis.system, target_crisis_id: crisis.id });
      // Others bolster
      for (let i = 1; i < clients.length; i++) {
        clients[i].action('bolster', { target_system: 'shields' });
      }
    } else {
      for (const c of clients) c.action('bolster', { target_system: 'shields' });
    }
  } else if (strategy === 'fix-all') {
    // Assign players to fix crises first, then bolster
    let playerIdx = 0;
    for (const crisis of crises) {
      for (let i = 0; i < crisis.crew_required && playerIdx < clients.length; i++) {
        clients[playerIdx].action('fix', {
          target_system: crisis.system,
          target_crisis_id: crisis.id,
        });
        playerIdx++;
      }
    }
    // Remaining players bolster
    while (playerIdx < clients.length) {
      clients[playerIdx].action('bolster', { target_system: 'shields' });
      playerIdx++;
    }
  } else {
    // no-fix: everyone bolsters
    for (const c of clients) c.action('bolster', { target_system: 'shields' });
  }

  // Wait for all players to receive the next round's state
  const currentRound = state.round_number;
  await Promise.all(
    clients.map((c) =>
      c.waitForState((s) => s.round_number === currentRound + 1 || s.phase === 'finale' || s.phase === 'results')
    )
  );
}

export async function playFinaleRound(
  clients: WsClient[],
  strategy: 'all-run' | 'some-carry' | 'all-hold' = 'all-run'
) {
  const state = clients[0].lastState!;
  const downed = state.players.filter((p) => p.is_down && p.escape_track < 3);
  const standing = state.players.filter((p) => !p.is_down && p.escape_track < 3);

  if (strategy === 'all-run') {
    for (const p of standing) {
      const client = clients.find((c) => c.playerId === p.id);
      client?.action('run');
    }
  } else if (strategy === 'some-carry' && downed.length > 0) {
    // 2 players carry, rest run
    const carriers = standing.slice(0, 2);
    for (const p of carriers) {
      const client = clients.find((c) => c.playerId === p.id);
      client?.action('carry', { target_player_id: downed[0].id });
    }
    for (const p of standing.slice(2)) {
      const client = clients.find((c) => c.playerId === p.id);
      client?.action('run');
    }
  } else if (strategy === 'all-hold') {
    for (const p of standing) {
      const client = clients.find((c) => c.playerId === p.id);
      client?.action('hold');
    }
  }

  // Wait for round advance or results
  const currentRound = state.round_number;
  await Promise.all(
    clients.map((c) =>
      c.waitForState((s) => s.round_number === currentRound + 1 || s.phase === 'results')
    )
  );
}