import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import nextConfig from "../../../next.config";

describe("T-19: next.config redirects", () => {
  it("redirects() maps /positions/import to /positions as a temporary redirect", async () => {
    expect(typeof nextConfig.redirects).toBe("function");
    const redirects = await nextConfig.redirects?.();
    expect(redirects).toContainEqual({
      source: "/positions/import",
      destination: "/positions",
      permanent: false,
    });
  });

  it("the old page file does not exist, so the redirect is the only thing serving that path", () => {
    const oldPage = fileURLToPath(new URL("../../positions/import/page.tsx", import.meta.url));
    expect(existsSync(oldPage)).toBe(false);
  });
});
