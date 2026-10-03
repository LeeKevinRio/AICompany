// In-memory registry of running game sessions (one per player). Sessions are lost on restart.

import { randomBytes } from 'node:crypto';
import { GameSession, HUMAN_SEAT, type ActionResponse } from '../game/session.js';
import type { PlayerRecord } from '../store/players.js';
import { ApiError, type Accounts } from './accounts.js';

const IDLE_TIMEOUT_MS = 2 * 60 * 60 * 1000;

export class GameManager {
  private readonly sessions = new Map<string, GameSession>();
  private readonly byPlayer = new Map<string, string>();
  private readonly sweeper: NodeJS.Timeout;

  constructor(private readonly accounts: Accounts) {
    this.sweeper = setInterval(() => this.sweep(), 10 * 60 * 1000);
    this.sweeper.unref();
  }

  /** Resume the player's unfinished game, or start a new one. */
  startOrResume(player: PlayerRecord): ActionResponse {
    const existing = this.activeFor(player);
    if (existing) return { steps: [], view: existing.view() };
    this.accounts.assertCanPlay(player);
    const id = `g_${randomBytes(8).toString('hex')}`;
    const session = new GameSession(id, player.id, player.nickname, {
      onHandEnd: (result) => this.accounts.recordHand(player, result, HUMAN_SEAT),
      coins: () => player.coins,
    });
    this.sessions.set(id, session);
    this.byPlayer.set(player.id, id);
    return this.finishIfOver(session, session.start());
  }

  view(player: PlayerRecord, gameId: string): ActionResponse {
    return { steps: [], view: this.owned(player, gameId).view() };
  }

  act(player: PlayerRecord, gameId: string, actionId: string): ActionResponse {
    const session = this.owned(player, gameId);
    return this.finishIfOver(session, session.act(actionId));
  }

  close(): void {
    clearInterval(this.sweeper);
  }

  private activeFor(player: PlayerRecord): GameSession | undefined {
    const id = this.byPlayer.get(player.id);
    const session = id ? this.sessions.get(id) : undefined;
    return session && !session.isOver ? session : undefined;
  }

  private owned(player: PlayerRecord, gameId: string): GameSession {
    const session = this.sessions.get(gameId);
    // Do not reveal whether someone else's game exists.
    if (!session || session.playerId !== player.id) throw new ApiError(404, 'GAME_NOT_FOUND', '找不到這場牌局');
    return session;
  }

  /** A finished game stays readable but no longer counts as the player's active game. */
  private finishIfOver(session: GameSession, response: ActionResponse): ActionResponse {
    if (session.isOver && this.byPlayer.get(session.playerId) === session.id) this.byPlayer.delete(session.playerId);
    return response;
  }

  private sweep(): void {
    const now = Date.now();
    for (const [id, s] of this.sessions) {
      if (now - s.lastActivity < IDLE_TIMEOUT_MS) continue;
      this.sessions.delete(id);
      if (this.byPlayer.get(s.playerId) === id) this.byPlayer.delete(s.playerId);
    }
  }
}
