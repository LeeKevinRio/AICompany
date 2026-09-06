import { describe, expect, it } from "vitest";
import type { DirectionWeight } from "../types";
import { actionDirectionMap, directionShares, ruleDirection } from "../ruleDirection";

const weights: DirectionWeight[] = [
  { direction: "defensive", weight: 0.6, actions: ["reduce", "stop_loss"] },
  { direction: "neutral", weight: 0.4, actions: ["hold"] },
];

describe("ruleDirection — read back from direction_weights, never re-derived", () => {
  it("maps each listed action to its direction; unknown actions → null", () => {
    const map = actionDirectionMap(weights);
    expect(map.get("reduce")).toBe("defensive");
    expect(map.get("stop_loss")).toBe("defensive");
    expect(map.get("hold")).toBe("neutral");
    expect(ruleDirection({ direction_weights: weights }, "add")).toBeNull();
    expect(ruleDirection({ direction_weights: [] }, "hold")).toBeNull();
  });

  it("first listing wins if an action were ever listed twice", () => {
    const map = actionDirectionMap([
      { direction: "defensive", weight: 1, actions: ["x"] },
      { direction: "constructive", weight: 1, actions: ["x"] },
    ]);
    expect(map.get("x")).toBe("defensive");
  });

  it("shares sum to 100 in response order; zero total → all 0", () => {
    const shares = directionShares(weights);
    expect(shares.map((s) => s.direction)).toEqual(["defensive", "neutral"]);
    expect(shares[0]!.sharePct).toBeCloseTo(60);
    expect(shares[1]!.sharePct).toBeCloseTo(40);
    expect(directionShares([{ direction: "neutral", weight: 0, actions: ["hold"] }])[0]!.sharePct).toBe(0);
    expect(directionShares([])).toEqual([]);
  });
});
