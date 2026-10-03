// Guest accounts, coins and leaderboard rules (independent of HTTP).

import { createHash, randomBytes } from 'node:crypto';
import { ECONOMY } from '../engine/rules.js';
import type { HandResult } from '../engine/types.js';
import { newPlayerId, type PlayerRecord, type PlayerRepository } from '../store/players.js';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export interface PlayerDto {
  id: string;
  nickname: string;
  coins: number;
  handsPlayed: number;
  handsWon: number;
  selfDraws: number;
  dealIns: number;
  bestTai: number;
}

export interface LeaderboardEntry {
  rank: number;
  nickname: string;
  coins: number;
  handsWon: number;
  bestTai: number;
  isMe: boolean;
}

export const NICKNAME_MAX = 12;
const LEADERBOARD_SIZE = 50;

export function hashToken(token: string): string {
  return createHash('sha256').update(token).digest('hex');
}

export function toPlayerDto(p: PlayerRecord): PlayerDto {
  return {
    id: p.id,
    nickname: p.nickname,
    coins: p.coins,
    handsPlayed: p.handsPlayed,
    handsWon: p.handsWon,
    selfDraws: p.selfDraws,
    dealIns: p.dealIns,
    bestTai: p.bestTai,
  };
}

export class Accounts {
  constructor(private readonly repo: PlayerRepository) {}

  createGuest(): { token: string; player: PlayerRecord } {
    const token = randomBytes(32).toString('base64url');
    const player: PlayerRecord = {
      id: newPlayerId(),
      nickname: `訪客${String(randomBytes(2).readUInt16LE(0) % 10000).padStart(4, '0')}`,
      tokenHash: hashToken(token),
      coins: ECONOMY.startingCoins,
      handsPlayed: 0,
      handsWon: 0,
      selfDraws: 0,
      dealIns: 0,
      bestTai: 0,
      reliefCount: 0,
      createdAt: new Date().toISOString(),
    };
    this.repo.create(player);
    return { token, player };
  }

  authenticate(authorization: string | undefined): PlayerRecord | undefined {
    const m = /^Bearer ([A-Za-z0-9_-]{16,128})$/.exec(authorization ?? '');
    if (!m) return undefined;
    return this.repo.getByTokenHash(hashToken(m[1]!));
  }

  rename(player: PlayerRecord, raw: unknown): PlayerRecord {
    const nickname = typeof raw === 'string' ? raw.trim() : '';
    const length = [...nickname].length;
    // Reject control and invisible formatting characters.
    if (length < 1 || length > NICKNAME_MAX || /[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u.test(nickname)) {
      throw new ApiError(400, 'INVALID_NICKNAME', `暱稱需為 1–${NICKNAME_MAX} 個字，且不能包含控制字元`);
    }
    player.nickname = nickname;
    this.repo.save(player);
    return player;
  }

  relief(player: PlayerRecord): PlayerRecord {
    if (player.coins >= ECONOMY.minCoinsToPlay) {
      throw new ApiError(400, 'RELIEF_NOT_ELIGIBLE', `金幣低於 ${ECONOMY.minCoinsToPlay.toLocaleString()} 才能領救濟金`);
    }
    player.coins = ECONOMY.reliefAmount;
    player.reliefCount++;
    this.repo.save(player);
    return player;
  }

  assertCanPlay(player: PlayerRecord): void {
    if (player.coins < ECONOMY.minCoinsToPlay) {
      throw new ApiError(400, 'NOT_ENOUGH_COINS', `金幣不足 ${ECONOMY.minCoinsToPlay.toLocaleString()}，請先領救濟金`);
    }
  }

  /** Apply one finished hand to the human player (seat `seat`). */
  recordHand(player: PlayerRecord, result: HandResult, seat: number): void {
    player.coins += result.deltas[seat]!;
    player.handsPlayed++;
    if (result.kind === 'win' && result.winnerSeat === seat) {
      player.handsWon++;
      if (result.selfDraw) player.selfDraws++;
      player.bestTai = Math.max(player.bestTai, result.totalTai);
    }
    if (result.kind === 'win' && result.loserSeat === seat) player.dealIns++;
    this.repo.save(player);
  }

  leaderboard(me: PlayerRecord | undefined): LeaderboardEntry[] {
    return this.repo
      .all()
      .sort((a, b) => b.coins - a.coins || b.handsWon - a.handsWon || a.createdAt.localeCompare(b.createdAt))
      .slice(0, LEADERBOARD_SIZE)
      .map((p, i) => ({
        rank: i + 1,
        nickname: p.nickname,
        coins: p.coins,
        handsWon: p.handsWon,
        bestTai: p.bestTai,
        isMe: me?.id === p.id,
      }));
  }
}
