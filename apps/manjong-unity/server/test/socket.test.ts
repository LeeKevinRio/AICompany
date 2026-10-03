import type { FastifyInstance } from 'fastify';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import WebSocket from 'ws';
import { hashToken } from '../src/api/accounts.js';
import { buildApp } from '../src/api/app.js';
import { isComplete, shanten } from '../src/engine/hand.js';
import { codeOf, KIND_COUNT, toCounts } from '../src/engine/tiles.js';
import { JsonPlayerRepository } from '../src/store/players.js';

// Loose message shape for assertions.
/* eslint-disable @typescript-eslint/no-explicit-any */
type Msg = any;

let app: FastifyInstance;
let repo: JsonPlayerRepository;
let base: string;

beforeEach(async () => {
  repo = new JsonPlayerRepository(null);
  ({ app } = await buildApp({ repo, corsOrigin: true, aiDelayMs: 0, wsMessagesPer10s: 100_000 }));
  await app.listen({ port: 0, host: '127.0.0.1' });
  const addr = app.server.address();
  if (!addr || typeof addr === 'string') throw new Error('no address');
  base = `127.0.0.1:${addr.port}`;
});

afterEach(async () => {
  await app.close();
});

class Client {
  readonly messages: Msg[] = [];
  private cursor = 0;
  private wake: (() => void) | null = null;
  readonly closed: Promise<number>;

  private constructor(readonly ws: WebSocket) {
    ws.on('message', (data) => {
      this.messages.push(JSON.parse(data.toString()));
      this.wake?.();
    });
    this.closed = new Promise((resolve) => ws.on('close', (code) => resolve(code)));
  }

  static async open(): Promise<Client> {
    const ws = new WebSocket(`ws://${base}/ws`);
    await new Promise<void>((resolve, reject) => {
      ws.once('open', () => resolve());
      ws.once('error', reject);
    });
    return new Client(ws);
  }

  send(msg: Record<string, unknown>): void {
    this.ws.send(JSON.stringify({ type: '', token: '', actionId: '', ...msg }));
  }

  /** Next unconsumed message matching `pred`; messages before it are consumed too. */
  async next(pred: (m: Msg) => boolean = () => true, timeoutMs = 5000): Promise<Msg> {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      while (this.cursor < this.messages.length) {
        const m = this.messages[this.cursor++];
        if (pred(m)) return m;
      }
      const left = deadline - Date.now();
      if (left <= 0) throw new Error('timed out waiting for message; last: ' + JSON.stringify(this.messages.slice(-2).map((m) => ({ type: m.type, code: m.code, ev: m.step?.event, phase: m.view?.phase ?? m.step?.view?.phase, opts: m.view?.options?.map((o: Msg) => o.id) }))));
      await new Promise<void>((resolve) => {
        const t = setTimeout(resolve, left);
        this.wake = () => {
          clearTimeout(t);
          resolve();
        };
      });
    }
  }

  close(): void {
    this.ws.close();
  }
}

async function guest(): Promise<string> {
  const res = await app.inject({ method: 'POST', url: '/api/auth/guest', payload: {} });
  return res.json().token as string;
}

async function login(token?: string): Promise<{ client: Client; token: string }> {
  const t = token ?? (await guest());
  const client = await Client.open();
  client.send({ type: 'auth', token: t });
  const ok = await client.next();
  expect(ok.type).toBe('auth_ok');
  return { client, token: t };
}

// ---- independent re-computation of what the server should tell the player ----

function count(tiles: string[], t: string): number {
  return tiles.filter((x) => x === t).length;
}

function bruteWaits(concealed: string[], sets: number): string[] {
  const waits: string[] = [];
  for (let k = 0; k < KIND_COUNT; k++) {
    const t = codeOf(k);
    if (count(concealed, t) >= 4) continue;
    if (isComplete(toCounts([...concealed, t]), sets)) waits.push(t);
  }
  return waits;
}

function visible(view: Msg): string[] {
  const me = view.players[view.mySeat];
  const seen = [...me.hand, ...(me.drawnTile ? [me.drawnTile] : [])];
  for (const p of view.players) {
    seen.push(...p.discards);
    for (const m of p.melds) seen.push(...m.tiles);
  }
  return seen;
}

function assertNoLeak(view: Msg): void {
  if (view.hasResult) return;
  for (const p of view.players) {
    if (p.seat === view.mySeat) continue;
    expect(p.hand).toEqual([]);
    expect(p.drawnTile).toBe('');
  }
}

interface Coverage {
  states: number;
  discardWithWaits: number;
  myWaitsShown: number;
  tsumo: number;
  ron: number;
  kongs: number;
  selfDraws: number;
  preempted: number;
}

/** Verifies every option the server offers against an independent computation. */
function verifyState(view: Msg, cov: Coverage): void {
  cov.states++;
  assertNoLeak(view);
  const me = view.players[view.mySeat];
  const sets = 5 - me.melds.length;
  const full: string[] = [...me.hand, ...(me.drawnTile ? [me.drawnTile] : [])];
  const seen = visible(view);
  const types = view.options.map((o: Msg) => o.type);

  for (const o of view.options) {
    expect(Array.isArray(o.waits)).toBe(true);
    expect(typeof o.tai).toBe('number');
    if (o.type === 'discard') {
      const rest = [...full];
      rest.splice(rest.indexOf(o.tile), 1);
      const expected = bruteWaits(rest, sets);
      expect(o.waits.map((w: Msg) => w.tile)).toEqual(expected);
      for (const w of o.waits) expect(w.left).toBe(Math.max(0, 4 - count(seen, w.tile)));
      if (expected.length > 0) {
        cov.discardWithWaits++;
        expect(o.label).toContain('聽');
      }
    } else if (o.type === 'tsumo') {
      expect(isComplete(toCounts(full), sets)).toBe(true);
      expect(o.tai).toBeGreaterThanOrEqual(0);
      expect(o.label).toContain(`${o.tai} 台`);
    } else if (o.type === 'ron') {
      expect(isComplete(toCounts([...full, o.tile]), sets)).toBe(true);
      expect(o.tai).toBeGreaterThanOrEqual(0);
    } else if (o.type === 'ankan') {
      expect(count(full, o.tile)).toBe(4);
    } else if (o.type === 'kakan') {
      expect(full).toContain(o.tile);
      expect(me.melds.some((m: Msg) => m.type === 'pon' && m.tiles[0] === o.tile)).toBe(true);
    } else {
      expect(o.tai).toBe(-1);
    }
  }

  // Completeness: whatever the server should offer after a draw, it does offer.
  if (me.drawnTile !== '') {
    if (isComplete(toCounts(full), sets)) expect(types).toContain('tsumo');
    if (view.wallRemaining > 0) {
      for (const t of new Set(full)) {
        if (count(full, t) === 4) expect(view.options.map((o: Msg) => o.id)).toContain(`ankan:${t}`);
      }
      for (const m of me.melds) {
        if (m.type === 'pon' && full.includes(m.tiles[0])) {
          expect(view.options.map((o: Msg) => o.id)).toContain(`kakan:${m.tiles[0]}`);
        }
      }
    }
  }

  // When it is not my discard, myWaits describes my current waits.
  if (!types.includes('discard') && view.phase === 'playing' && me.drawnTile === '') {
    const expected = me.hand.length === sets * 3 + 1 ? bruteWaits(me.hand, sets) : [];
    expect(view.myWaits.map((w: Msg) => w.tile)).toEqual(expected);
    if (expected.length > 0) cov.myWaitsShown++;
  } else {
    expect(view.myWaits).toEqual([]);
  }
}

function choose(view: Msg, cov: Coverage): Msg {
  const opts: Msg[] = view.options;
  const find = (t: string): Msg | undefined => opts.find((o) => o.type === t);
  const win = find('tsumo') ?? find('ron');
  if (win) return win;
  const next = find('next');
  if (next) return next;
  const kong = find('ankan') ?? find('kakan') ?? find('kan');
  if (kong) {
    cov.kongs++;
    return kong;
  }
  if (find('pass')) return find('pon') ?? find('pass');
  // Play sensibly (lowest shanten) so the test regularly reaches tenpai and wins.
  const me = view.players[view.mySeat];
  const full: string[] = [...me.hand, ...(me.drawnTile ? [me.drawnTile] : [])];
  const sets = 5 - me.melds.length;
  let best: Msg = null;
  let bestShanten = Infinity;
  for (const o of opts.filter((x) => x.type === 'discard')) {
    const rest = [...full];
    rest.splice(rest.indexOf(o.tile), 1);
    const sh = shanten(toCounts(rest), sets) - o.waits.length * 0.01;
    if (sh < bestShanten) {
      bestShanten = sh;
      best = o;
    }
  }
  return best;
}

describe('websocket game', () => {
  it('plays full games; every option, wait, kong, tai and drawn tile matches an independent check', { timeout: 600_000 }, async () => {
    const cov: Coverage = { states: 0, discardWithWaits: 0, myWaitsShown: 0, tsumo: 0, ron: 0, kongs: 0, selfDraws: 0, preempted: 0 };
    // WS_GAMES=200 npm test -- socket  runs a long verification pass (used before releases).
    const games = Number(process.env.WS_GAMES ?? 3);
    for (let game = 0; game < games; game++) {
      const { client, token } = await login();
      client.send({ type: 'start' });
      let pendingWin: Msg | null = null;
      for (let i = 0; i < 20000; i++) {
        const m = await client.next((x) => x.type === 'step' || x.type === 'state' || x.type === 'error');
        expect(m.type).not.toBe('error');
        if (m.type === 'step') {
          const { event, view } = m.step;
          assertNoLeak(view);
          expect(view.options).toEqual([]);
          if (event.type === 'draw') {
            if (event.seat === view.mySeat) {
              cov.selfDraws++;
              expect(event.tile).not.toBe('');
              expect(view.players[view.mySeat].drawnTile).toBe(event.tile);
            } else {
              expect(event.tile).toBe('');
            }
          }
          continue;
        }
        const view = m.view;
        if (pendingWin && view.hasResult) {
          if (view.result.winnerSeat === view.mySeat) {
            // The tai shown on the button is exactly what the settlement used.
            expect(view.result.totalTai).toBe(pendingWin.tai);
          } else {
            // Only a discard win can be pre-empted: a seat closer to the discarder also called ron (截胡).
            expect(pendingWin.type).toBe('ron');
            const discarder = view.result.loserSeat;
            const dist = (s: number): number => (s - discarder + 4) % 4;
            expect(dist(view.result.winnerSeat)).toBeLessThan(dist(view.mySeat));
            cov.preempted++;
          }
          pendingWin = null;
        }
        if (view.phase === 'game_end') break;
        verifyState(view, cov);
        const pick = choose(view, cov);
        expect(pick).toBeDefined();
        if (pick.type === 'tsumo' || pick.type === 'ron') {
          pendingWin = pick;
          if (pick.type === 'tsumo') cov.tsumo++;
          else cov.ron++;
        }
        client.send({ type: 'action', actionId: pick.id });
      }
      // Coins were settled server-side and pushed after each hand.
      const me = (await app.inject({ method: 'GET', url: '/api/me', headers: { authorization: `Bearer ${token}` } })).json().player;
      expect(me.handsPlayed).toBeGreaterThan(0);
      const lastPlayer = [...client.messages].reverse().find((x) => x.type === 'player');
      expect(lastPlayer.player.coins).toBe(me.coins);
      client.close();
    }
    expect(cov.selfDraws).toBeGreaterThan(0);
    if (games >= 50) {
      // A long pass must have exercised every kind of information the client relies on.
      expect(cov.discardWithWaits).toBeGreaterThan(0);
      expect(cov.myWaitsShown).toBeGreaterThan(0);
      expect(cov.tsumo + cov.ron).toBeGreaterThan(0);
      expect(cov.kongs).toBeGreaterThan(0);
    }
    // eslint-disable-next-line no-console
    console.log('coverage', cov);
  });

  it('rejects an illegal action with an error and a fresh state', async () => {
    const { client } = await login();
    client.send({ type: 'start' });
    await client.next((m) => m.type === 'state');
    client.send({ type: 'action', actionId: 'discard:XX' });
    const err = await client.next((m) => m.type === 'error');
    expect(err.code).toBe('ILLEGAL_ACTION');
    const state = await client.next((m) => m.type === 'state');
    expect(state.view.options.length).toBeGreaterThan(0);
    client.close();
  });

  it('requires auth first and closes with 4401 on a bad token', async () => {
    const a = await Client.open();
    a.send({ type: 'start' });
    expect((await a.next()).code).toBe('UNAUTHORIZED');
    expect(await a.closed).toBe(4401);
    const b = await Client.open();
    b.send({ type: 'auth', token: 'x'.repeat(40) });
    expect((await b.next()).code).toBe('UNAUTHORIZED');
    expect(await b.closed).toBe(4401);
  });

  it('a second connection replaces the first (4000) and resumes the same game', async () => {
    const first = await login();
    first.client.send({ type: 'start' });
    const s1 = await first.client.next((m) => m.type === 'state');
    const second = await login(first.token);
    expect(await first.client.closed).toBe(4000);
    second.client.send({ type: 'start' });
    const s2 = await second.client.next((m) => m.type === 'state');
    expect(s2.view.gameId).toBe(s1.view.gameId);
    expect(s2.view.options.map((o: Msg) => o.id)).toEqual(s1.view.options.map((o: Msg) => o.id));
    second.client.close();
  });

  it('refuses to start a game without enough coins, and answers ping', async () => {
    const { client, token } = await login();
    repo.getByTokenHash(hashToken(token))!.coins = 500;
    client.send({ type: 'start' });
    expect((await client.next()).code).toBe('NOT_ENOUGH_COINS');
    client.send({ type: 'action', actionId: 'pass' });
    expect((await client.next()).code).toBe('NO_GAME');
    client.send({ type: 'ping' });
    expect((await client.next()).type).toBe('pong');
    client.close();
  });

  it('every message carries every field (JsonUtility friendly)', async () => {
    const { client } = await login();
    client.send({ type: 'ping' });
    const m = await client.next();
    expect(Object.keys(m).sort()).toEqual(['code', 'message', 'player', 'seq', 'step', 'type', 'view']);
    client.close();
  });
});
