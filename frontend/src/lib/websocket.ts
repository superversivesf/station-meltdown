import type { ServerMessage, ClientMessage } from './types';

export class GameWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnect = 5;
  private listeners: ((msg: ServerMessage) => void)[] = [];
  private statusListeners: ((status: 'connected' | 'disconnected' | 'reconnecting') => void)[] = [];

  constructor(roomCode: string) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    this.url = `${protocol}//${host}/ws/${roomCode}`;
  }

  connect() {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.notifyStatus('connected');
    };
    this.ws.onmessage = (event) => {
      const msg: ServerMessage = JSON.parse(event.data);
      this.listeners.forEach((fn) => fn(msg));
    };
    this.ws.onclose = () => {
      this.notifyStatus('disconnected');
      if (this.reconnectAttempts < this.maxReconnect) {
        this.reconnectAttempts++;
        this.notifyStatus('reconnecting');
        setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
      }
    };
    this.ws.onerror = () => {
      this.ws?.close();
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
    this.maxReconnect = 0;
    this.ws?.close();
  }
}