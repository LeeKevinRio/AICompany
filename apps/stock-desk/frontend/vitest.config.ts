import { defineConfig } from "vitest/config";

/**
 * Minimal test setup for the Phase 8 FR-C1 operation-summary wording guard
 * (see `app/lib/__tests__/`). No `@testing-library/react` / jsdom yet — this
 * project's first frontend test suite covers pure data-transform functions
 * and a wording-file lint scan, both of which run happily under plain
 * Node. See `work/stock-desk-phase8-需求.md`'s FR-C1 handoff notes for the
 * "no test framework existed yet" trade-off this file resolves.
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["app/**/*.test.ts"],
  },
});
