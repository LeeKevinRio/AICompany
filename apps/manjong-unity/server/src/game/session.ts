// One human (seat 0) against three AI seats. The server paces the AI: every event is pushed to the
// listener as it happens, and a fresh `state` snapshot is published whenever the human owes a decision
// or a hand ends. The same shape works for real multiplayer later.

import { AI_PROFILES, chooseAction } from '../ai/ai.js';
import {
  applyAction,
  createGame,
  nextHand,
  optionsFor,
  pendingSeats,
  type GameEvent,
  type GameState,
} from '../engine/engine.js';
import { createRng, type Rng } from '../engine/rng.js';
import type { HandResult } from '../engine/types.js';
import { buildView, toEventDto, viewerOptions, type EventDto, type GameViewDto, type SeatInfo } from './view.js';

export const HUMAN_SEAT = 0;

export interface Step {
  event: EventDto;
  view: GameViewDto;
}

export interface SessionHooks {
  /** Called once per finished hand, before the hand-end view is built. */
  onHandEnd(result: HandResult, game: GameState): void;
  /** The human's persistent coin balance. */
  coins(): number;
  /** Every event, in order, with the view right after it (no options). */
  onStep(step: Step): void;
  /** Authoritative snapshot (with options) whenever the AI stops: human decision, hand end or game end. */
  onState(view: GameViewDto): void;
  /** The AI loop failed unexpectedly. */
  onError(error: unknown): void;
}

export interface SessionOptions {
  seed?: number;
  /** Pause before each AI move, in ms (0 in tests). */
  aiDelayMs?: number;
}

const SEATS: SeatInfo[] = [
  { avatar: 'me', isAi: false },
  ...AI_PROFILES.map((p) => ({ avatar: p.avatar, isAi: true })),
];

/** Safety valve: a hand needs far fewer AI moves than this. */
const MAX_AI_MOVES = 2_000;

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

export class BusyError extends Error {
  constructor() {
    super('The AI is still playing');
  }
}

export class GameSession {
  readonly game: GameState;
  lastActivity = Date.now();
  private readonly aiRng: Rng;
  private readonly aiDelayMs: number;
  private pumping: Promise<void> | null = null;
  private disposed = false;

  constructor(
    readonly id: string,
    readonly playerId: string,
    humanName: string,
    private readonly hooks: SessionHooks,
    options: SessionOptions = {},
  ) {
    const { seed } = options;
    this.aiRng = createRng(seed === undefined ? undefined : seed ^ 0x5bd1e995);
    this.aiDelayMs = options.aiDelayMs ?? 0;
    const names = [humanName, ...AI_PROFILES.map((p) => p.name)];
    this.game = createGame({ id, names, seed });
  }

  /** Deal the first hand and let the AI play up to the first human decision. */
  start(): void {
    nextHand(this.game, (e) => this.record(e));
    this.pump();
  }

  /**
   * Apply the human's action (validated by the engine) and let the AI continue.
   * Throws IllegalActionError when the id is not a current option, BusyError while the AI is playing.
   */
  act(actionId: string): void {
    this.lastActivity = Date.now();
    if (this.pumping) throw new BusyError();
    if (actionId === 'next' && viewerOptions(this.game, HUMAN_SEAT).some((o) => o.id === 'next')) {
      nextHand(this.game, (e) => this.record(e));
    } else {
      applyAction(this.game, HUMAN_SEAT, actionId, (e) => this.record(e));
    }
    this.pump();
  }

  view(): GameViewDto {
    return buildView(this.game, HUMAN_SEAT, SEATS, this.hooks.coins(), true);
  }

  get isOver(): boolean {
    return this.game.over && this.game.hand.phase.type === 'ended';
  }

  /** True while the AI is still playing (the human cannot act yet). */
  get isBusy(): boolean {
    return this.pumping !== null;
  }

  /** Resolves once the AI has stopped (tests, shutdown). */
  async idle(): Promise<void> {
    while (this.pumping) await this.pumping;
  }

  dispose(): void {
    this.disposed = true;
  }

  private record(event: GameEvent): void {
    if ((event.type === 'win' || event.type === 'exhaustive') && this.game.hand.result) {
      this.hooks.onHandEnd(this.game.hand.result, this.game);
    }
    this.hooks.onStep({
      event: toEventDto(event, HUMAN_SEAT),
      view: buildView(this.game, HUMAN_SEAT, SEATS, this.hooks.coins(), false),
    });
  }

  private pump(): void {
    if (this.pumping) return;
    this.pumping = (async () => {
      // Always yield first so callers finish their own bookkeeping before events flow.
      await Promise.resolve();
      let state: GameViewDto | null;
      try {
        state = await this.runAi();
      } catch (err) {
        this.pumping = null;
        this.hooks.onError(err);
        return;
      }
      // Clear the busy flag before publishing, so a listener may act on the new state immediately.
      this.pumping = null;
      if (state) this.hooks.onState(state);
    })();
  }

  /** Plays AI seats until the human owes a decision or the hand ends; returns the snapshot to publish. */
  private async runAi(): Promise<GameViewDto | null> {
    for (let moves = 0; moves < MAX_AI_MOVES; moves++) {
      if (this.disposed) return null;
      const pending = pendingSeats(this.game);
      if (this.game.hand.phase.type === 'ended' || pending.length === 0 || pending.includes(HUMAN_SEAT)) {
        return this.view();
      }
      if (this.aiDelayMs > 0) await sleep(this.aiDelayMs);
      if (this.disposed) return null;
      const seat = pending[0]!;
      const profile = AI_PROFILES[seat - 1]!;
      const action = chooseAction(this.game, seat, optionsFor(this.game, seat), profile.avatar, this.aiRng);
      applyAction(this.game, seat, action, (e) => this.record(e));
    }
    throw new Error('AI did not reach a human decision');
  }
}
