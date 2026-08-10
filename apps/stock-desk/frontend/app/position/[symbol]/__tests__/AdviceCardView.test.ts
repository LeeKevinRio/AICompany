/**
 * 波次1文案裁決.md「D 批」複審 (2026-08-10): the opposing-direction sentence
 * (「本次同時命中方向相反的規則…」) was gated on
 * `direction_weights.length > 1`, which also fires for defensive + neutral —
 * a `hold` bucket is a third category, not an opposite side, so that gate
 * claimed an opposition the data does not show. `hasOpposingDirections`
 * requires both actual sides. The sentence itself is unchanged.
 */

import { describe, expect, it } from "vitest";
import type { AdviceCard, DirectionWeight } from "../../../lib/types";
import { hasOpposingDirections } from "../AdviceCardView";

function makeAdvice(directions: DirectionWeight[]): AdviceCard {
  return { direction_weights: directions } as AdviceCard;
}

function dw(direction: string): DirectionWeight {
  return { direction, weight: 1, actions: [] };
}

describe("hasOpposingDirections — D2 真對立條件", () => {
  it("is false for defensive + neutral: 中性 is not an opposing side", () => {
    expect(hasOpposingDirections(makeAdvice([dw("defensive"), dw("neutral")]))).toBe(false);
  });

  it("is true for defensive + constructive: a real opposition", () => {
    expect(hasOpposingDirections(makeAdvice([dw("defensive"), dw("constructive")]))).toBe(true);
  });

  it("is false for constructive + neutral", () => {
    expect(hasOpposingDirections(makeAdvice([dw("constructive"), dw("neutral")]))).toBe(false);
  });

  it("is false for a single direction, and for none at all", () => {
    expect(hasOpposingDirections(makeAdvice([dw("defensive")]))).toBe(false);
    expect(hasOpposingDirections(makeAdvice([]))).toBe(false);
  });

  it("is still true when a neutral bucket sits alongside both real sides", () => {
    const advice = makeAdvice([dw("defensive"), dw("constructive"), dw("neutral")]);
    expect(hasOpposingDirections(advice)).toBe(true);
  });
});
