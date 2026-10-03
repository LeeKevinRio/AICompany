// HTTP API (contract: work/manjong-unity/api-contract.md).

import cors from '@fastify/cors';
import fastifyStatic from '@fastify/static';
import Fastify, { type FastifyInstance, type FastifyRequest } from 'fastify';
import { existsSync } from 'node:fs';
import { extname, resolve } from 'node:path';
import { IllegalActionError } from '../engine/engine.js';
import type { PlayerRecord, PlayerRepository } from '../store/players.js';
import { Accounts, ApiError, toPlayerDto } from './accounts.js';
import { GameManager } from './games.js';

export interface AppOptions {
  repo: PlayerRepository;
  /** Allowed CORS origins; `true` reflects any origin (development). */
  corsOrigin: string[] | true;
  /** Directory of a Unity WebGL build to serve at "/", if present. */
  webglDir?: string;
  logger?: boolean;
}

const actionSchema = {
  body: {
    type: 'object',
    required: ['actionId'],
    additionalProperties: false,
    properties: { actionId: { type: 'string', minLength: 1, maxLength: 32 } },
  },
} as const;

const nicknameSchema = {
  body: {
    type: 'object',
    required: ['nickname'],
    additionalProperties: false,
    properties: { nickname: { type: 'string', maxLength: 64 } },
  },
} as const;

const gameParams = {
  params: {
    type: 'object',
    required: ['id'],
    properties: { id: { type: 'string', pattern: '^g_[0-9a-f]{16}$' } },
  },
} as const;

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
  const games = new GameManager(accounts);

  await app.register(cors, {
    origin: options.corsOrigin,
    methods: ['GET', 'POST'],
    allowedHeaders: ['Content-Type', 'Authorization'],
  });

  app.setErrorHandler((error, request, reply) => {
    if (error instanceof ApiError) {
      return reply.status(error.status).send({ error: { code: error.code, message: error.message } });
    }
    if (error instanceof IllegalActionError) {
      return reply.status(400).send({ error: { code: 'ILLEGAL_ACTION', message: '這個動作現在不能做' } });
    }
    const status = (error as { statusCode?: number }).statusCode;
    if (status && status >= 400 && status < 500) {
      return reply.status(status).send({ error: { code: 'BAD_REQUEST', message: '請求格式不正確' } });
    }
    request.log.error(error);
    return reply.status(500).send({ error: { code: 'INTERNAL', message: '伺服器發生錯誤' } });
  });

  const requirePlayer = (request: FastifyRequest): PlayerRecord => {
    const player = accounts.authenticate(request.headers.authorization);
    if (!player) throw new ApiError(401, 'UNAUTHORIZED', '請重新登入');
    return player;
  };

  app.get('/api/health', async () => ({ ok: true }));

  app.post('/api/auth/guest', async () => {
    const { token, player } = accounts.createGuest();
    return { token, player: toPlayerDto(player) };
  });

  app.get('/api/me', async (request) => ({ player: toPlayerDto(requirePlayer(request)) }));

  app.post('/api/me/nickname', { schema: nicknameSchema }, async (request) => {
    const { nickname } = request.body as { nickname: string };
    return { player: toPlayerDto(accounts.rename(requirePlayer(request), nickname)) };
  });

  app.post('/api/me/relief', async (request) => ({ player: toPlayerDto(accounts.relief(requirePlayer(request))) }));

  app.get('/api/leaderboard', async (request) => ({
    entries: accounts.leaderboard(accounts.authenticate(request.headers.authorization)),
  }));

  app.post('/api/games', async (request) => games.startOrResume(requirePlayer(request)));

  app.get('/api/games/:id', { schema: gameParams }, async (request) => {
    const { id } = request.params as { id: string };
    return games.view(requirePlayer(request), id);
  });

  app.post('/api/games/:id/actions', { schema: { ...gameParams, ...actionSchema } }, async (request) => {
    const { id } = request.params as { id: string };
    const { actionId } = request.body as { actionId: string };
    return games.act(requirePlayer(request), id, actionId);
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
