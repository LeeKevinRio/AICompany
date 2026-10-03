// WebSocket protocol for games (contract: work/manjong-unity/api-contract.md §2).

import type { WebSocket } from 'ws';
import { IllegalActionError } from '../engine/engine.js';
import { BusyError } from '../game/session.js';
import type { PlayerRecord } from '../store/players.js';
import { ApiError, toPlayerDto, type Accounts } from './accounts.js';
import type { GameManager, GameSink } from './games.js';

const AUTH_TIMEOUT_MS = 10_000;
const CLOSE_UNAUTHORIZED = 4401;
const CLOSE_REPLACED = 4000;
const CLOSE_FORBIDDEN_ORIGIN = 4403;
/** Default flood guard: more client messages than this per 10 s closes the connection. */
export const DEFAULT_MESSAGES_PER_10S = 100;

interface ClientMessage {
  type?: unknown;
  token?: unknown;
  actionId?: unknown;
}

/** Live connections by player, so a new login can replace an old one. */
const connections = new Map<string, WebSocket>();

export function handleGameSocket(
  socket: WebSocket,
  origin: string | undefined,
  allowedOrigins: string[] | true,
  accounts: Accounts,
  games: GameManager,
  maxMessagesPer10s = DEFAULT_MESSAGES_PER_10S,
): void {
  if (allowedOrigins !== true && origin !== undefined && !allowedOrigins.includes(origin)) {
    socket.close(CLOSE_FORBIDDEN_ORIGIN, 'origin not allowed');
    return;
  }

  let seq = 0;
  let player: PlayerRecord | undefined;
  let sink: GameSink | undefined;
  let windowStart = Date.now();
  let windowCount = 0;

  // Every message carries every field (JsonUtility friendly); unused ones are empty objects / strings.
  const send = (type: string, fields: Record<string, unknown> = {}): void => {
    if (socket.readyState !== socket.OPEN) return;
    seq++;
    socket.send(JSON.stringify({ type, seq, player: {}, step: {}, view: {}, code: '', message: '', ...fields }));
  };
  const sendError = (code: string, message: string): void => send('error', { code, message });

  const authTimer = setTimeout(() => {
    if (player) return;
    sendError('UNAUTHORIZED', '請先登入');
    socket.close(CLOSE_UNAUTHORIZED, 'auth timeout');
  }, AUTH_TIMEOUT_MS);

  const resync = (): void => {
    if (!player) return;
    const view = games.view(player);
    if (view) send('state', { view });
  };

  const onAuth = (token: unknown): void => {
    const found = typeof token === 'string' ? accounts.authenticate(`Bearer ${token}`) : undefined;
    if (!found) {
      sendError('UNAUTHORIZED', '登入已失效，請重新登入');
      socket.close(CLOSE_UNAUTHORIZED, 'bad token');
      return;
    }
    clearTimeout(authTimer);
    player = found;
    const previous = connections.get(found.id);
    if (previous && previous !== socket) previous.close(CLOSE_REPLACED, 'logged in elsewhere');
    connections.set(found.id, socket);
    sink = {
      step: (step) => send('step', { step }),
      state: (view) => send('state', { view }),
      player: (p) => send('player', { player: p }),
      error: sendError,
    };
    games.attach(found.id, sink);
    send('auth_ok', { player: toPlayerDto(found) });
  };

  socket.on('message', (raw, isBinary) => {
    const now = Date.now();
    if (now - windowStart > 10_000) {
      windowStart = now;
      windowCount = 0;
    }
    if (++windowCount > maxMessagesPer10s) {
      socket.close(1008, 'too many messages');
      return;
    }

    let msg: ClientMessage;
    try {
      if (isBinary) throw new Error('binary');
      msg = JSON.parse(raw.toString()) as ClientMessage;
      if (typeof msg !== 'object' || msg === null) throw new Error('not an object');
    } catch {
      sendError('BAD_MESSAGE', '訊息格式不正確');
      return;
    }

    if (msg.type === 'ping') {
      send('pong');
      return;
    }
    if (msg.type === 'auth') {
      if (!player) onAuth(msg.token);
      return;
    }
    if (!player) {
      sendError('UNAUTHORIZED', '請先登入');
      socket.close(CLOSE_UNAUTHORIZED, 'not authenticated');
      return;
    }

    try {
      if (msg.type === 'start') {
        games.start(player);
      } else if (msg.type === 'action') {
        if (typeof msg.actionId !== 'string' || msg.actionId.length === 0 || msg.actionId.length > 32) {
          sendError('BAD_MESSAGE', '訊息格式不正確');
          return;
        }
        games.act(player, msg.actionId);
      } else {
        sendError('BAD_MESSAGE', '不支援的訊息類型');
      }
    } catch (err) {
      if (err instanceof ApiError) {
        sendError(err.code, err.message);
      } else if (err instanceof BusyError) {
        sendError('ILLEGAL_ACTION', '請等其他玩家動作完');
      } else if (err instanceof IllegalActionError) {
        sendError('ILLEGAL_ACTION', '這個動作現在不能做');
        resync();
      } else {
        console.error('[ws] unexpected error:', err);
        sendError('INTERNAL', '伺服器發生錯誤');
      }
    }
  });

  socket.on('close', () => {
    clearTimeout(authTimer);
    if (player && sink) games.detach(player.id, sink);
    if (player && connections.get(player.id) === socket) connections.delete(player.id);
  });
}
