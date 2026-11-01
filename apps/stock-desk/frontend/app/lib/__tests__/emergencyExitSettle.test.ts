/**
 * FE-T7 (tech-architect Q14): the emergency-exit mutation's settle behaviour,
 * driven through a plain `MutationObserver` with the API module mocked.
 *
 * Pins FR-8a / FE-C13: on success *and* on failure `/today` is cancelled and
 * then invalidated — in that order — and the mutation's own ending does not
 * wait for `/today` to come back (otherwise 「送出中」 would last as long as the
 * refetch, and the submit lock would stay held).
 */

import { MutationObserver, QueryClient } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import { createExitReceiptStore } from "../exitReceiptStore";
import type { ExitReceiptStore } from "../exitReceiptStore";
import { emergencyExitMutationOptions } from "../queries";
import type { PlaybookEmergencyExitResponse } from "../types";

const postPlaybookEmergencyExit = vi.hoisted(() => vi.fn());

vi.mock("../api", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api")>();
  return { ...original, postPlaybookEmergencyExit };
});

function response(): PlaybookEmergencyExitResponse {
  return {
    executed_at: "2026-08-11",
    execution_date: "2026-08-12",
    total_shares: 500,
    freeze_until: "2026-09-08",
    message: "message",
    mode_reason: "mode reason",
    attribution: null,
    directives: [],
    pending_directives: [],
    warnings: [],
    as_of: "2026-08-11",
  };
}

let client: QueryClient;
let store: ExitReceiptStore;
let order: string[];
/** A refetch that never answers: the mutation must not wait for it. */
const neverSettles = (): Promise<void> => new Promise<void>(() => {});

beforeEach(() => {
  postPlaybookEmergencyExit.mockReset();
  client = new QueryClient();
  store = createExitReceiptStore();
  order = [];
  vi.spyOn(client, "cancelQueries").mockImplementation(() => {
    order.push("cancel");
    return neverSettles();
  });
  vi.spyOn(client, "invalidateQueries").mockImplementation(() => {
    order.push("invalidate");
    return neverSettles();
  });
});

describe("emergencyExitMutationOptions().onSettled", () => {
  it("cancels then invalidates ['playbook-today'] when the exit is accepted, without awaiting either", async () => {
    postPlaybookEmergencyExit.mockResolvedValue(response());
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));

    const result = await observer.mutate();

    expect(result.message).toBe("message");
    expect(order).toEqual(["cancel", "invalidate"]);
    expect(client.cancelQueries).toHaveBeenCalledWith({ queryKey: ["playbook-today"] });
    expect(client.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["playbook-today"] });
    expect(observer.getCurrentResult().status).toBe("success");
  });

  it("does the same when the exit fails (5xx), and the failure still reaches the caller", async () => {
    postPlaybookEmergencyExit.mockRejectedValue(new ApiError("server error", 500));
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));

    await expect(observer.mutate()).rejects.toBeInstanceOf(ApiError);

    expect(order).toEqual(["cancel", "invalidate"]);
    expect(observer.getCurrentResult().status).toBe("error");
  });

  it("does the same for a network-level failure that is not an ApiError", async () => {
    postPlaybookEmergencyExit.mockRejectedValue(new TypeError("Failed to fetch"));
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));

    await expect(observer.mutate()).rejects.toBeInstanceOf(TypeError);

    expect(order).toEqual(["cancel", "invalidate"]);
  });

  it("returns nothing, so the mutation resolves while /today is still outstanding", () => {
    const options = emergencyExitMutationOptions(client, store);
    expect(options.onSettled()).toBeUndefined();
    expect(order).toEqual(["cancel", "invalidate"]);
  });

  it("calls the mutate-level callbacks while the observer is subscribed, even though /today never answers", async () => {
    postPlaybookEmergencyExit.mockRejectedValue(new ApiError("server error", 500));
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    const unsubscribe = observer.subscribe(() => {});
    const onSettled = vi.fn();
    const onError = vi.fn();

    await observer.mutate(undefined, { onSettled, onError }).catch(() => undefined);

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onSettled).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it("drops the mutate-level callbacks when the observer has no listener (why the observer lives at page level, VETO-2)", async () => {
    // This is the failure the old structure had: the status bar (and with it the
    // observer) unmounted when /today failed, so `setStep("idle")` and the lock
    // release in the callbacks never ran.
    postPlaybookEmergencyExit.mockResolvedValue(response());
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    const onSuccess = vi.fn();

    await observer.mutate(undefined, { onSuccess });

    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("records the accepted response in the receipt store from the hook-level onSuccess, even with no observer listening (風控 FE-2)", async () => {
    // The page may be gone by the time the response lands (browser back while the
    // request is in flight). Mutate-level callbacks are dropped then (previous
    // test); the hook-level onSuccess belongs to the mutation and still runs.
    postPlaybookEmergencyExit.mockResolvedValue(response());
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    expect(observer.hasListeners()).toBe(false);

    await observer.mutate();

    expect(store.getSnapshot()).toEqual({ seq: 1, response: response() });
  });

  it("does not record a receipt when the exit fails", async () => {
    postPlaybookEmergencyExit.mockRejectedValue(new ApiError("server error", 500));
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    await observer.mutate().catch(() => undefined);
    expect(store.getSnapshot()).toBeNull();
  });

  it("a second accepted response replaces the first and advances the sequence", async () => {
    postPlaybookEmergencyExit.mockResolvedValueOnce(response());
    postPlaybookEmergencyExit.mockResolvedValueOnce({ ...response(), message: "second" });
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    await observer.mutate();
    await observer.mutate();
    expect(store.getSnapshot()?.seq).toBe(2);
    expect(store.getSnapshot()?.response.message).toBe("second");
  });

  it("records the receipt before the settle step, and neither awaits /today", async () => {
    postPlaybookEmergencyExit.mockResolvedValue(response());
    const seen: string[] = [];
    store.subscribe(() => seen.push("receipt"));
    vi.mocked(client.cancelQueries).mockImplementation(() => {
      seen.push("cancel");
      return neverSettles();
    });
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    await observer.mutate();
    expect(seen[0]).toBe("receipt");
    expect(seen).toContain("cancel");
  });
});
