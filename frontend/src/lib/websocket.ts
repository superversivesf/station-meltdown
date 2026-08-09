import type { ServerMessage, ClientMessage } from './types';

// Persist the server-assigned player id per room so a reconnect (network
// blip, page refresh mid-game) can reclaim the same slot instead of adding
// a duplicate player. The backend uppercases room codes, so normalize here
// to keep the storage key consistent with the server's room identity.
const PLAYER_ID_KEY = (roomCode: string) => `station_meltdown_player_id:${roomCode.toUpperCase()}`;

export class GameWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private roomCode: string;
  private name: string | null = null;
  private playerId: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnect = 5;
  private closed = false;
  private listeners: ((msg: ServerMessage) => void)[] = [];
  private statusListeners: ((status: 'connected' | 'disconnected' | 'reconnecting') => void)[] = [];

  constructor(roomCode: string) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    this.roomCode = roomCode.toUpperCase();
    this.url = `${protocol}//${host}/ws/${this.roomCode}`;
    this.playerId = window.localStorage.getItem(PLAYER_ID_KEY(this.roomCode));
  }

  join(name: string): void {
    this.name = name;
    this.send(this.joinMessage());
  }

  private joinMessage(): ClientMessage {
    return {
      type: 'join',
      name: this.name ?? 'Unknown',
      // Empty string would be treated as a present-but-blank id by the
      // server, so only send it when we actually have one.
      player_id: this.playerId || undefined,
    };
  }

  connect() {
    // Capture the socket in a local so a second connect() can't leave the
    // previous socket's handlers pointing at a newer `this.ws`.
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.notifyStatus('connected');
      if (this.name !== null) {
        // Reclaim the same slot if this is a reconnect; player_id is read
        // fresh from storage so a reload mid-game rejoins as the same player.
        this.send(this.joinMessage());
      }
    };
    ws.onmessage = (event) => {
      const msg: ServerMessage = JSON.parse(event.data);
      if (msg.type === 'state') {
        // Adopt the server-assigned id and remember it for reconnect.
        this.playerId = msg.player_id;
        window.localStorage.setItem(PLAYER_ID_KEY(this.roomCode), this.playerId);
      }
      this.listeners.forEach((fn) => fn(msg));
    };
    ws.onclose = () => {
      // Ignore close events from superseded sockets (e.g. a stale socket
      // closing after a reconnect already replaced it).
      if (ws !== this.ws) return;
      this.notifyStatus('disconnected');
      if (!this.closed && this.reconnectAttempts < this.maxReconnect) {
        this.reconnectAttempts++;
        this.notifyStatus('reconnecting');
        setTimeout(() => {
          // A close() during the backoff must cancel the pending reconnect
          // — otherwise the timer outlives the page and leaks a socket.
          if (!this.closed) this.connect();
        }, 1000 * this.reconnectAttempts);
      }
    };
    ws.onerror = () => {
      // Close the failing socket; onclose handles the reconnect.
      ws.close();
    };
  }

  send(msg: ClientMessage) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  onMessage(fn: (msg: ServerMessage) => void) {
    this.listeners.push(fn);
  }

  onStatusChange(fn: (status: 'connected' | 'disconnected' | 'reconnecting') => void) {
    this.statusListeners.push(fn);
  }

  private notifyStatus(status: 'connected' | 'disconnected' | 'reconnecting') {
    this.statusListeners.forEach((fn) => fn(status));
  }

  close() {
    this.closed = true;
    this.maxReconnect = 0;
    this.ws?.close();
    this.ws = null;
    this.listeners = [];
    this.statusListeners = [];
  }
}