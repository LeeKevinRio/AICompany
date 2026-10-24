/**
 * `request()` (`app/lib/api.ts`) adds `CLIENT_HEADER` to every state-changing
 * request, because the backend's cross-site write guard
 * (`app/api/client_header.py`) refuses unsafe methods without it. Reads must
 * not carry it, so they stay simple requests with no CORS preflight.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CLIENT_HEADER, ackAlertEvent, deletePosition, getHealth, importPositionsCsv } from "../api";

function sentHeaders(fetchMock: ReturnType<typeof vi.fn<typeof fetch>>): Record<string, string> {
  const init = fetchMock.mock.calls[0]?.[1];
  return (init?.headers ?? {}) as Record<string, string>;
}

describe("request() client header", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is sent on a body-less POST", async () => {
    await ackAlertEvent(1);
    expect(sentHeaders(fetchMock)[CLIENT_HEADER]).toBe("1");
  });

  it("is sent on a multipart POST", async () => {
    await importPositionsCsv(new File(["symbol\n"], "p.csv", { type: "text/csv" }));
    expect(sentHeaders(fetchMock)[CLIENT_HEADER]).toBe("1");
  });

  it("is sent on a DELETE", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await deletePosition(1);
    expect(sentHeaders(fetchMock)[CLIENT_HEADER]).toBe("1");
  });

  it("is not sent on a GET", async () => {
    await getHealth();
    expect(sentHeaders(fetchMock)).not.toHaveProperty(CLIENT_HEADER);
  });
});
