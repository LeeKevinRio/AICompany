/**
 * `resolveDirectorySymbol` (`app/lib/api.ts`) maps a directory miss to
 * `null`. The backend reports a miss as `200` + `found: false`
 * (`app/api/directory.py`'s `ResolveMiss`); a `404` from an older backend is
 * still read as a miss. Anything else must still throw, never be laundered
 * into "not in the directory".
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, resolveDirectorySymbol } from "../api";
import type { DirectoryItem } from "../types";

const HIT: DirectoryItem = {
  symbol: "2330",
  name: "TEST_NAME",
  market: "TW",
  source: "twse_openapi",
  as_of: "2026-08-09T12:00:00+00:00",
  sector: null,
  sector_source: null,
  sector_as_of: null,
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("resolveDirectorySymbol", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the item unchanged on a hit", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, HIT));

    await expect(resolveDirectorySymbol("2330")).resolves.toEqual(HIT);
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/api\/directory\/resolve\/2330$/);
  });

  it("returns null on a 200 `found: false` miss", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, {
        found: false,
        symbol: "9999X",
        directory_synced: true,
        as_of: "2026-10-06T00:00:00+00:00",
      }),
    );

    await expect(resolveDirectorySymbol("9999X")).resolves.toBeNull();
  });

  it("returns null on a `found: false` miss from an un-synced directory", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, {
        found: false,
        symbol: "2330",
        directory_synced: false,
        as_of: "2026-10-06T00:00:00+00:00",
      }),
    );

    await expect(resolveDirectorySymbol("2330")).resolves.toBeNull();
  });

  it("still returns null on a 404 from an older backend", async () => {
    fetchMock.mockResolvedValue(jsonResponse(404, { detail: "TEST_DETAIL" }));

    await expect(resolveDirectorySymbol("9999X")).resolves.toBeNull();
  });

  it("throws ApiError on a 5xx instead of treating it as a miss", async () => {
    fetchMock.mockResolvedValue(jsonResponse(500, { detail: "TEST_DETAIL" }));

    const result = resolveDirectorySymbol("2330");
    await expect(result).rejects.toBeInstanceOf(ApiError);
    await expect(result).rejects.toMatchObject({ status: 500 });
  });

  it("throws ApiError on a network failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("network down"));

    await expect(resolveDirectorySymbol("2330")).rejects.toMatchObject({ status: 0 });
  });

  it("URL-encodes the symbol", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, HIT));

    await resolveDirectorySymbol("A B/C");
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/api\/directory\/resolve\/A%20B%2FC$/);
  });
});
