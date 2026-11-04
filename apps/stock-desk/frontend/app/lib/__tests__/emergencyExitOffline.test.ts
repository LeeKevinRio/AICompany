/**
 * FE-R2 (風控 2026-11-01, 資料 `ADR-0037殘留與r32-風控.md` 第 2 項): what the
 * emergency-exit mutation does when the browser reports it is offline.
 *
 * Standing guard test: it exercises a real `QueryClient` and `MutationObserver`
 * against TanStack's real `onlineManager`, so a package bump that changes how
 * `networkMode` pauses a mutation shows up here. The online state is restored
 * after every test -- `onlineManager` is process-wide.
 *
 * Why it matters: with the default `networkMode: 'online'` an offline submit sits
 * `pending` + `isPaused` (the button says 「送出中…」 and nothing was sent; 取消
 * and Esc are locked) and is sent by itself once the connection returns --
 * possibly after the user left the page or crossed Taipei midnight. That is an
 * irreversible confirmation carrying stale facts. `'always'` sends now, fails at
 * once offline, and the NB-6 panel is shown.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { MutationObserver, QueryClient, onlineManager } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createExitReceiptStore } from "../exitReceiptStore";
import { emergencyExitMutationOptions } from "../queries";
import type { PlaybookEmergencyExitResponse } from "../types";

const postPlaybookEmergencyExit = vi.hoisted(() => vi.fn());

vi.mock("../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api")>();
  return { ...original, postPlaybookEmergencyExit };
});

let client: QueryClient;
let wasOnline: boolean;

beforeEach(() => {
  wasOnline = onlineManager.isOnline();
  postPlaybookEmergencyExit.mockReset();
  client = new QueryClient();
});

afterEach(() => {
  onlineManager.setOnline(wasOnline);
  client.clear();
});

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
  await new Promise<void>((r) => setTimeout(r, 0));
}

describe("emergency exit while the browser reports offline (FE-R2)", () => {
  it("sends once, fails at once with the network error, is never paused, and is not re-sent on reconnect", async () => {
    onlineManager.setOnline(false);
    postPlaybookEmergencyExit.mockRejectedValue(new TypeError("Failed to fetch"));
    const observer = new MutationObserver(
      client,
      emergencyExitMutationOptions(client, createExitReceiptStore()),
    );
    const seen: Array<{ status: string; isPaused: boolean }> = [];
    const unsubscribe = observer.subscribe((result) => {
      seen.push({ status: result.status, isPaused: result.isPaused });
    });

    await expect(observer.mutate()).rejects.toBeInstanceOf(TypeError);
    await settle();

    expect(postPlaybookEmergencyExit).toHaveBeenCalledTimes(1);
    expect(observer.getCurrentResult().status).toBe("error");
    expect(observer.getCurrentResult().isPaused).toBe(false);
    expect(seen.length).toBeGreaterThan(0);
    for (const state of seen) expect(state.isPaused).toBe(false);
    expect(seen.map((s) => s.status)).toContain("pending");

    // Connection returns: nothing is sent behind the user's back.
    onlineManager.setOnline(true);
    await client.resumePausedMutations();
    await settle();
    expect(postPlaybookEmergencyExit).toHaveBeenCalledTimes(1);
    expect(client.getMutationCache().getAll().filter((m) => m.state.isPaused)).toEqual([]);
    unsubscribe();
  });

  it("an offline failure records no receipt", async () => {
    onlineManager.setOnline(false);
    postPlaybookEmergencyExit.mockRejectedValue(new TypeError("Failed to fetch"));
    const store = createExitReceiptStore();
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    await observer.mutate().catch(() => undefined);
    expect(store.getSnapshot().receipt).toBeNull();
  });

  it("a retry by the user afterwards (back online) sends exactly one more request", async () => {
    onlineManager.setOnline(false);
    postPlaybookEmergencyExit.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    postPlaybookEmergencyExit.mockResolvedValueOnce({ message: "ok" } as PlaybookEmergencyExitResponse);
    const store = createExitReceiptStore();
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    await observer.mutate().catch(() => undefined);
    onlineManager.setOnline(true);
    await observer.mutate();
    expect(postPlaybookEmergencyExit).toHaveBeenCalledTimes(2);
    expect(store.getSnapshot().receipt?.seq).toBe(1);
  });

  it("control: without `networkMode: 'always'` the same offline submit would be paused and never sent (the premise of the VETO)", async () => {
    onlineManager.setOnline(false);
    postPlaybookEmergencyExit.mockResolvedValue({ message: "late" } as PlaybookEmergencyExitResponse);
    const { networkMode: _dropped, ...withDefault } = emergencyExitMutationOptions(
      client,
      createExitReceiptStore(),
    );
    expect(_dropped).toBe("always");
    const observer = new MutationObserver(client, withDefault);
    const unsubscribe = observer.subscribe(() => {});
    void observer.mutate().catch(() => undefined);
    await settle();

    expect(observer.getCurrentResult().status).toBe("pending");
    expect(observer.getCurrentResult().isPaused).toBe(true);
    expect(postPlaybookEmergencyExit).not.toHaveBeenCalled();
    unsubscribe();
  });
});

describe("the emergency-exit options carry `networkMode: 'always'` and nothing that defers a submit (FE-R1, FE-C24)", () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const strip = (text: string) => text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  const queries = strip(readFileSync(resolve(here, "../queries.ts"), "utf-8"));
  const factory = queries.slice(
    queries.indexOf("export function emergencyExitMutationOptions("),
    queries.indexOf("export function useEmergencyExit("),
  );

  it("the factory sets networkMode 'always' exactly once, and no retry / scope / mutationKey", () => {
    expect(factory.match(/networkMode:\s*"always" as const/g)).toHaveLength(1);
    expect(factory).not.toMatch(/\bretry\b|\bretryDelay\b|\bscope\b|\bmutationKey\b/);
    expect(factory).not.toMatch(/networkMode:\s*"online"|networkMode:\s*"offlineFirst"/);
  });

  it("it is the only networkMode in the file, and no global default carries one", () => {
    expect(queries.match(/networkMode/g)).toHaveLength(1);
    const providers = strip(readFileSync(resolve(here, "../../providers.tsx"), "utf-8"));
    expect(providers).not.toMatch(/networkMode|defaultOptions|setMutationDefaults|mutationCache/);
    expect(providers).toContain("new QueryClient()");
  });
});
