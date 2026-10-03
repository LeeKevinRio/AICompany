// HTTP surface: health check, WebSocket endpoint and optional WebGL static files.
// Everything else goes through the WebSocket protocol (contract: work/manjong-unity/api-contract.md).

import cors from '@fastify/cors';
import fastifyStatic from '@fastify/static';
import websocket from '@fastify/websocket';
import Fastify, { type FastifyInstance } from 'fastify';
import { existsSync } from 'node:fs';
import { extname, resolve } from 'node:path';
import type { PlayerRepository } from '../store/players.js';
import { Accounts, ApiError } from './accounts.js';
import { GameManager } from './games.js';
import { handleGameSocket } from './socket.js';

export interface AppOptions {
  repo: PlayerRepository;
  /** Allowed CORS origins; `true` reflects any origin (development). */
  corsOrigin: string[] | true;
  /** Directory of a Unity WebGL build to serve at "/", if present. */
  webglDir?: string;
  logger?: boolean;
  /** Pause before each AI move (ms). */
  aiDelayMs?: number;
  /** WebSocket flood guard (client messages per 10 s); raised in tests that play at machine speed. */
  wsMessagesPer10s?: number;
  /** How long a new connection may stay unauthenticated (ms); shortened in tests. */
  wsAuthTimeoutMs?: number;
}

// Unity WebGL builds may be pre-compressed; serve them with the matching encoding.
const ENCODINGS: Record<string, string> = { '.gz': 'gzip', '.br': 'br' };
const INNER_TYPES: Record<string, string> = {
  '.js': 'application/javascript',
  '.wasm': 'application/wasm',
  '.data': 'application/octet-stream',
  '.json': 'application/json',
};

export async function buildApp(options: AppOptions): Promise<{ app: FastifyInstance; games: GameManager }> {
  const app = Fastify({ logger: options.logger ?? false, bodyLimit: 16 * 1024 });
  const accounts = new Accounts(options.repo);
  const games = new GameManager(accounts, { aiDelayMs: options.aiDelayMs ?? 0 });

  await app.register(websocket, { options: { maxPayload: 4 * 1024 } });
  await app.register(cors, {
    origin: options.corsOrigin,
    methods: ['GET'],
    allowedHeaders: ['Content-Type', 'Authorization'],
  });

  app.setErrorHandler((error, request, reply) => {
    if (error instanceof ApiError) {
      return reply.status(error.status).send({ error: { code: error.code, message: error.message } });
    }
    const status = (error as { statusCode?: number }).statusCode;
    if (status && status >= 400 && status < 500) {
      return reply.status(status).send({ error: { code: 'BAD_REQUEST', message: '請求格式不正確' } });
    }
    request.log.error(error);
    return reply.status(500).send({ error: { code: 'INTERNAL', message: '伺服器發生錯誤' } });
  });

  app.get('/api/health', async () => ({ ok: true }));

  app.get('/ws', { websocket: true }, (socket, request) => {
    handleGameSocket(
      socket,
      request.headers.origin,
      options.corsOrigin,
      accounts,
      games,
      options.wsMessagesPer10s,
      options.wsAuthTimeoutMs,
    );
  });

  if (options.webglDir && existsSync(resolve(options.webglDir, 'index.html'))) {
    await app.register(fastifyStatic, {
      root: resolve(options.webglDir),
      setHeaders: (res, path) => {
        const encoding = ENCODINGS[extname(path)];
        if (!encoding) return;
        res.header('Content-Encoding', encoding);
        const inner = extname(path.slice(0, -extname(path).length));
        res.header('Content-Type', INNER_TYPES[inner] ?? 'application/octet-stream');
      },
    });
  }

  app.addHook('onClose', async () => games.close());
  return { app, games };
}
