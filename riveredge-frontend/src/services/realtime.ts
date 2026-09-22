/**
 * 实时推送（REALTIME_BACKEND=socketio | centrifugo | noop）
 */

import { apiRequest } from './api';

export interface RealtimeConfig {
  enabled: boolean;
  backend: 'noop' | 'socketio' | 'centrifugo' | string;
  ws_url: string;
  socket_path: string;
}

export interface RealtimeToken {
  token: string;
  channel: string;
}

export interface RealtimeEnvelope {
  event?: string;
  payload?: Record<string, unknown>;
  ts?: string;
}

export async function getRealtimeConfig(): Promise<RealtimeConfig> {
  return apiRequest<RealtimeConfig>('/core/realtime/config', { method: 'GET' });
}

export async function getRealtimeToken(): Promise<RealtimeToken> {
  return apiRequest<RealtimeToken>('/core/realtime/token', { method: 'GET' });
}

export function resolveRealtimeWsUrl(config: RealtimeConfig): string {
  const explicit = (config.ws_url || '').trim();
  if (explicit) {
    return explicit.replace(/\/$/, '');
  }
  if (typeof window === 'undefined') {
    return '';
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/connection/websocket`;
}

export function resolveSocketIoOrigin(): string {
  if (typeof window === 'undefined') {
    return '';
  }
  return window.location.origin;
}
