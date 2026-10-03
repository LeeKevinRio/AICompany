// One human (seat 0) against three AI seats. Runs the AI until the human owes a decision,
// recording every event together with the view right after it so the client can replay them.

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

export interface ActionResponse {
  steps: Step[];
  view: GameViewDto;
}

export interface SessionHooks {
  /** Called once per finished hand, before the hand-end view is built. */
  onHandEnd(result: HandResult, game: GameState): void;
  /** The human's persistent coin balance. */
  coins(): number;
}

const SEATS: SeatInfo[] = [
  { avatar: 'me', isAi: false },
  ...AI_PROFILES.map((p) => ({ avatar: p.avatar, isAi: true })),
];

/** Safety valve: a hand needs far fewer AI moves than this. */
const MAX_AI_MOVES = 2_000;

export class GameSession {
  readonly game: GameState;
  lastActivity = Date.now();
  private steps: Step[] = [];
  private readonly aiRng: Rng;

  constructor(
    readonly id: string,
    readonly playerId: string,
    humanName: string,
    private readonly hooks: SessionHooks,
    seed?: number,
  ) {
    this.aiRng = createRng(seed === undefined ? undefined : seed ^ 0x5bd1e995);
    const names = [humanName, ...AI_PROFILES.map((p) => p.name)];
    this.game = createGame({ id, names, seed });
  }

  /** Steps produced while creating the game (deal + AI moves up to the first human decision). */
  start(): ActionResponse {
    nextHand(this.game, (e) => this.record(e));
    this.runAi();
    return this.flush();
  }

  act(actionId: string): ActionResponse {
    this.lastActivity = Date.now();
    if (actionId === 'next' && viewerOptions(this.game, HUMAN_SEAT).some((o) => o.id === 'next')) {
      nextHand(this.game, (e) => this.record(e));
    } else {
      applyAction(this.game, HUMAN_SEAT, actionId, (e) => this.record(e));
    }
    this.runAi();
    return this.flush();
  }

  view(): GameViewDto {
    return buildView(this.game, HUMAN_SEAT, SEATS, this.hooks.coins(), true);
  }

  get isOver(): boolean {
    return this.game.over && this.game.hand.phase.type === 'ended';
  }

  private record(event: GameEvent): void {
    if ((event.type === 'win' || event.type === 'exhaustive') && this.game.hand.result) {
      this.hooks.onHandEnd(this.game.hand.result, this.game);
    }
    this.steps.push({
      event: toEventDto(event, HUMAN_SEAT),
      view: buildView(this.game, HUMAN_SEAT, SEATS, this.hooks.coins(), false),
    });
  }

  private runAi(): void {
    for (let moves = 0; moves < MAX_AI_MOVES; moves++) {
      if (this.game.hand.phase.type === 'ended') return;
      const pending = pendingSeats(this.game);
      if (pending.length === 0 || pending.includes(HUMAN_SEAT)) return;
      const seat = pending[0]!;
      const profile = AI_PROFILES[seat - 1]!;
      const action = chooseAction(this.game, seat, optionsFor(this.game, seat), profile.avatar, this.aiRng);
      applyAction(this.game, seat, action, (e) => this.record(e));
    }
    throw new Error('AI did not reach a human decision');
  }

  private flush(): ActionResponse {
    const steps = this.steps;
    this.steps = [];
    return { steps, view: this.view() };
  }
}
