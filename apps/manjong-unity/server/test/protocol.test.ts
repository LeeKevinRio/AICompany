// Protocol guards that the play-through tests deliberately relax (auth timeout, origin, flood, payload, busy).
import type { FastifyInstance } from 'fastify';
import { afterEach, describe, expect, it } from 'vitest';
import WebSocket from 'ws';
import { buildApp, type AppOptions } from '../src/api/app.js';
import { JsonPlayerRepository } from '../src/store/players.js';

/* eslint-disable @typescript-eslint/no-explicit-any */
let app: FastifyInstance | null = null;

afterEach(async () => {
  await app?.close();
  app = null;
});

async function start(opts: Partial<AppOptions>): Promise<string> {
  ({ app } = await buildApp({ repo: new JsonPlayerRepository(null), corsOrigin: true, ...opts }));
  await app.listen({ port: 0, host: '127.0.0.1' });
  const addr = app.server.address();
  if (!addr || typeof addr === 'string') throw new Error('no address');
  return `ws://127.0.0.1:${addr.port}/ws`;
}

function connect(url: string, headers: Record<string, string> = {}): Promise<{ ws: WebSocket; messages: any[]; closed: Promise<number> }> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url, { headers });
    const messages: any[] = [];
    ws.on('message', (d) => messages.push(JSON.parse(d.toString())));
    const closed = new Promise<number>((r) => ws.on('close', (code) => r(code)));
    ws.once('open', () => resolve({ ws, messages, closed }));
    ws.once('error', reject);
  });
}

async function waitFor(messages: any[], pred: (m: any) => boolean, timeoutMs = 5000): Promise<any> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const m = messages.find(pred);
    if (m) return m;
    await new Promise((r) => setTimeout(r, 10));
  }
  throw new Error('timed out');
}

describe('websocket protocol guards', () => {
  it('AUTH_TIMEOUT closes with 4408 (distinct from INVALID_TOKEN / 4401)', async () => {
    const url = await start({ wsAuthTimeoutMs: 100 });
    const c = await connect(url);
    expect(await c.closed).toBe(4408);
    expect(c.messages.at(-1)).toMatchObject({ type: 'error', code: 'AUTH_TIMEOUT' });
  });

  it('rejects a browser Origin that is not allowed (4403); allows listed ones and non-browser clients', async () => {
    const url = await start({ corsOrigin: ['http://good.example'] });
    const bad = await connect(url, { Origin: 'http://evil.example' });
    expect(await bad.closed).toBe(4403);
    const good = await connect(url, { Origin: 'http://good.example' });
    good.ws.send(JSON.stringify({ type: 'ping' }));
    expect((await waitFor(good.messages, (m) => m.type === 'pong')).type).toBe('pong');
    good.ws.close();
    const native = await connect(url);
    native.ws.send(JSON.stringify({ type: 'ping' }));
    await waitFor(native.messages, (m) => m.type === 'pong');
    native.ws.close();
  });

  it('closes a flooding connection with 1008', async () => {
    const url = await start({});
    const c = await connect(url);
    for (let i = 0; i < 101; i++) c.ws.send(JSON.stringify({ type: 'ping' }));
    expect(await c.closed).toBe(1008);
  });

  it('closes on an oversized message (1009)', async () => {
    const url = await start({});
    const c = await connect(url);
    c.ws.send(JSON.stringify({ type: 'ping', pad: 'x'.repeat(8 * 1024) }));
    expect(await c.closed).toBe(1009);
  });

  it('an action while the AI is still playing is rejected; the state still arrives once the AI stops', async () => {
    const url = await start({ aiDelayMs: 150 });
    const c = await connect(url);
    c.ws.send(JSON.stringify({ type: 'guest' }));
    await waitFor(c.messages, (m) => m.type === 'auth_ok');
    c.ws.send(JSON.stringify({ type: 'start' }));
    // Wait until the AI is mid-play (some step arrived, no state yet), unless the human acts first.
    const first = await waitFor(c.messages, (m) => m.type === 'step' || m.type === 'state');
    if (first.type === 'state') return; // the dealer was the human and nothing to pace; nothing to test this run
    c.ws.send(JSON.stringify({ type: 'action', actionId: 'pass', requestId: 'busy' }));
    const err = await waitFor(c.messages, (m) => m.replyTo === 'busy');
    expect(err).toMatchObject({ type: 'error', code: 'ILLEGAL_ACTION' });
    const state = await waitFor(c.messages, (m) => m.type === 'state', 15000);
    expect(state.view.options.length).toBeGreaterThan(0);
    c.ws.close();
  }, 20000);
});
