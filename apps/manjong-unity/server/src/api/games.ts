// In-memory registry of running game sessions (one per player) and the socket each player is
// currently attached to. Sessions survive disconnects; they are lost on server restart.

import { randomBytes } from 'node:crypto';
import { GameSession, HUMAN_SEAT, type Step } from '../game/session.js';
import type { GameViewDto } from '../game/view.js';
import type { PlayerRecord } from '../store/players.js';
import { ApiError, toPlayerDto, type Accounts, type PlayerDto } from './accounts.js';

const IDLE_TIMEOUT_MS = 2 * 60 * 60 * 1000;

/** Where a player's game messages go (one WebSocket connection). */
export interface GameSink {
  step(step: Step): void;
  state(view: GameViewDto): void;
  player(player: PlayerDto): void;
  error(code: string, message: string): void;
}

export interface GameManagerOptions {
  aiDelayMs: number;
}

export class GameManager {
  private readonly sessions = new Map<string, GameSession>();
  private readonly byPlayer = new Map<string, string>();
  private readonly sinks = new Map<string, GameSink>();
  private readonly sweeper: NodeJS.Timeout;

  constructor(
    private readonly accounts: Accounts,
    private readonly options: GameManagerOptions,
  ) {
    this.sweeper = setInterval(() => this.sweep(), 10 * 60 * 1000);
    this.sweeper.unref();
  }

  /** Route this player's game messages to `sink` (replaces any previous connection). */
  attach(playerId: string, sink: GameSink): void {
    this.sinks.set(playerId, sink);
  }

  detach(playerId: string, sink: GameSink): void {
    if (this.sinks.get(playerId) === sink) this.sinks.delete(playerId);
  }

  /** Resume the player's unfinished game (publishes its state), or start a new one. */
  start(player: PlayerRecord): void {
    const existing = this.activeFor(player);
    if (existing) {
      existing.lastActivity = Date.now();
      // While the AI is still playing, the state is published when it stops.
      if (!existing.isBusy) this.sinks.get(player.id)?.state(existing.view());
      return;
    }
    this.accounts.assertCanPlay(player);
    const id = `g_${randomBytes(8).toString('hex')}`;
    const sinkOf = (): GameSink | undefined => this.sinks.get(player.id);
    const session: GameSession = new GameSession(
      id,
      player.id,
      player.nickname,
      {
        onHandEnd: (result) => this.accounts.recordHand(player, result, HUMAN_SEAT),
        coins: () => player.coins,
        onStep: (step) => sinkOf()?.step(step),
        onState: (view) => {
          sinkOf()?.state(view);
          if (view.hasResult) sinkOf()?.player(toPlayerDto(player));
          this.releaseIfOver(session);
        },
        onError: (err) => {
          console.error(`[game ${id}] AI loop failed:`, err);
          sinkOf()?.error('INTERNAL', '伺服器發生錯誤，請重新開始牌局');
        },
      },
      { aiDelayMs: this.options.aiDelayMs },
    );
    this.sessions.set(id, session);
    this.byPlayer.set(player.id, id);
    session.start();
  }

  act(player: PlayerRecord, actionId: string): void {
    const session = this.activeFor(player);
    if (!session) throw new ApiError(404, 'NO_GAME', '沒有進行中的牌局，請重新開始');
    session.act(actionId);
  }

  /** Current snapshot of the player's active game, if any (used to resync after a rejected action). */
  view(player: PlayerRecord): GameViewDto | undefined {
    const session = this.activeFor(player);
    return session && !session.isBusy ? session.view() : undefined;
  }

  session(player: PlayerRecord): GameSession | undefined {
    return this.activeFor(player);
  }

  close(): void {
    clearInterval(this.sweeper);
    for (const s of this.sessions.values()) s.dispose();
  }

  private activeFor(player: PlayerRecord): GameSession | undefined {
    const id = this.byPlayer.get(player.id);
    return id ? this.sessions.get(id) : undefined;
  }

  /** A finished game no longer counts as the player's active game. */
  private releaseIfOver(session: GameSession): void {
    if (!session.isOver) return;
    if (this.byPlayer.get(session.playerId) === session.id) this.byPlayer.delete(session.playerId);
    this.sessions.delete(session.id);
  }

  private sweep(): void {
    const now = Date.now();
    for (const [id, s] of this.sessions) {
      if (now - s.lastActivity < IDLE_TIMEOUT_MS) continue;
      s.dispose();
      this.sessions.delete(id);
      if (this.byPlayer.get(s.playerId) === id) this.byPlayer.delete(s.playerId);
    }
  }
}
