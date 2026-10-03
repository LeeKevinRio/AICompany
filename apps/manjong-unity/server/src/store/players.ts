// Player persistence. JSON file with atomic writes for the prototype (see ADR-M001);
// everything goes through PlayerRepository so it can be swapped for a database later.

import { randomBytes } from 'node:crypto';
import { mkdirSync, readFileSync, renameSync, writeFileSync, existsSync } from 'node:fs';
import { dirname } from 'node:path';

export interface PlayerRecord {
  id: string;
  nickname: string;
  tokenHash: string;
  coins: number;
  handsPlayed: number;
  handsWon: number;
  selfDraws: number;
  dealIns: number;
  bestTai: number;
  reliefCount: number;
  createdAt: string;
}

export interface PlayerRepository {
  create(record: PlayerRecord): void;
  getById(id: string): PlayerRecord | undefined;
  getByTokenHash(hash: string): PlayerRecord | undefined;
  /** Persist changes made to a record returned by this repository. */
  save(record: PlayerRecord): void;
  all(): PlayerRecord[];
  close(): void;
}

interface FileShape {
  version: 1;
  players: PlayerRecord[];
}

export function newPlayerId(): string {
  return `p_${randomBytes(8).toString('hex')}`;
}

/**
 * In-memory repository, optionally backed by a JSON file. Writes are debounced and atomic
 * (write to a temp file, then rename) so a crash never leaves a half-written file.
 */
export class JsonPlayerRepository implements PlayerRepository {
  private readonly byId = new Map<string, PlayerRecord>();
  private readonly byToken = new Map<string, PlayerRecord>();
  private timer: NodeJS.Timeout | null = null;
  private dirty = false;

  constructor(
    private readonly filePath: string | null,
    private readonly flushDelayMs = 200,
  ) {
    if (filePath && existsSync(filePath)) {
      const data = JSON.parse(readFileSync(filePath, 'utf8')) as Partial<FileShape>;
      if (data.version !== 1 || !Array.isArray(data.players)) {
        throw new Error(`Unrecognised player data file: ${filePath}`);
      }
      for (const p of data.players) this.index(p);
    }
  }

  create(record: PlayerRecord): void {
    if (this.byId.has(record.id)) throw new Error('Duplicate player id');
    this.index(record);
    this.scheduleFlush();
  }

  getById(id: string): PlayerRecord | undefined {
    return this.byId.get(id);
  }

  getByTokenHash(hash: string): PlayerRecord | undefined {
    return this.byToken.get(hash);
  }

  save(record: PlayerRecord): void {
    if (this.byId.get(record.id) !== record) throw new Error('Unknown player record');
    this.scheduleFlush();
  }

  all(): PlayerRecord[] {
    return [...this.byId.values()];
  }

  close(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.flush();
  }

  private index(record: PlayerRecord): void {
    this.byId.set(record.id, record);
    this.byToken.set(record.tokenHash, record);
  }

  private scheduleFlush(delayMs = this.flushDelayMs): void {
    this.dirty = true;
    if (!this.filePath || this.timer) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      try {
        this.flush();
      } catch (err) {
        // Keep serving from memory and retry later instead of crashing the process.
        console.error('[players] failed to save player data, retrying in 5s:', err);
        this.scheduleFlush(5_000);
      }
    }, delayMs);
  }

  private flush(): void {
    if (!this.filePath || !this.dirty) return;
    mkdirSync(dirname(this.filePath), { recursive: true });
    const tmp = `${this.filePath}.${process.pid}.tmp`;
    const data: FileShape = { version: 1, players: this.all() };
    writeFileSync(tmp, JSON.stringify(data, null, 2), { mode: 0o600 });
    renameSync(tmp, this.filePath);
    this.dirty = false;
  }
}
