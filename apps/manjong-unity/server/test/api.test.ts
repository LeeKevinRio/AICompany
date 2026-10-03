import type { FastifyInstance } from 'fastify';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/api/app.js';
import { JsonPlayerRepository } from '../src/store/players.js';

let app: FastifyInstance;

beforeEach(async () => {
  ({ app } = await buildApp({ repo: new JsonPlayerRepository(null), corsOrigin: true }));
});

afterEach(async () => {
  await app.close();
});

describe('http surface', () => {
  it('only exposes the health check; accounts and games live on the WebSocket', async () => {
    expect((await app.inject({ method: 'GET', url: '/api/health' })).json()).toEqual({ ok: true });
    for (const [method, url] of [
      ['POST', '/api/auth/guest'],
      ['GET', '/api/me'],
      ['GET', '/api/leaderboard'],
      ['POST', '/api/games'],
    ] as const) {
      expect((await app.inject({ method, url, payload: method === 'POST' ? {} : undefined })).statusCode).toBe(404);
    }
  });
});
