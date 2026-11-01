/**
 * FE-T7 and FE-T13/FE-T14 (tech-architect Q14, ADR-0037 D): the emergency-exit mutation's settle behaviour,
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
import { INITIAL_EXIT_RECEIPT_STATE, exitReceiptReducer } from "../exitReceipt";
import { createExitReceiptStore } from "../exitReceiptStore";
import type { ExitReceiptSink, ExitReceiptStore } from "../exitReceiptStore";
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
});

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Let the mutation's awaited steps (hook-level callbacks, state dispatch) run. */
async function flush(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
  await new Promise<void>((r) => setTimeout(r, 0));
}

describe("FE-T13: the FE-2 contract of the definition-level onSuccess (ADR-0037 FE-C4)", () => {
  it("(a) writes the receipt after the observer unmounted mid-flight, and the mutate-level onSuccess does not run", async () => {
    const request = deferred<PlaybookEmergencyExitResponse>();
    postPlaybookEmergencyExit.mockReturnValue(request.promise);
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    const unsubscribe = observer.subscribe(() => {});
    const mutateLevelOnSuccess = vi.fn();
    void observer.mutate(undefined, { onSuccess: mutateLevelOnSuccess }).catch(() => undefined);
    await flush();

    unsubscribe(); // the page has gone: browser back while the request is in flight
    expect(store.getSnapshot().receipt).toBeNull();

    request.resolve(response());
    await flush();

    expect(store.getSnapshot().receipt?.seq).toBe(1);
    expect(mutateLevelOnSuccess).not.toHaveBeenCalled(); // documents mutationObserver.ts:164
  });

  it("(b) the sink is called while the mutation is still pending, before success is dispatched", async () => {
    postPlaybookEmergencyExit.mockResolvedValue(response());
    const statusAtAccept: string[] = [];
    const running: MutationObserver<PlaybookEmergencyExitResponse, Error, void, unknown> =
      new MutationObserver(
        client,
        emergencyExitMutationOptions(client, {
          accept: (r) => {
            statusAtAccept.push(running.getCurrentResult().status);
            store.accept(r);
          },
        }),
      );
    await running.mutate();
    expect(statusAtAccept).toEqual(["pending"]);
    expect(running.getCurrentResult().status).toBe("success");
  });

  it("(d) a failed request leaves the store untouched", async () => {
    postPlaybookEmergencyExit.mockRejectedValue(new ApiError("server error", 500));
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    await observer.mutate().catch(() => undefined);
    expect(store.getSnapshot()).toEqual({ receipt: null, scrolledSeq: 0 });
  });
});

describe("FE-T14: an old page and a new page each submit; the last arrival wins in either order", () => {
  async function bothSubmit(arrivalOrder: "first-then-second" | "second-then-first") {
    const first = deferred<PlaybookEmergencyExitResponse>();
    const second = deferred<PlaybookEmergencyExitResponse>();
    postPlaybookEmergencyExit.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const accept = vi.spyOn(store, "accept");

    const oldPage = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    const newPage = new MutationObserver(client, emergencyExitMutationOptions(client, store));
    const unsubscribeOld = oldPage.subscribe(() => {});
    void oldPage.mutate().catch(() => undefined);
    await flush();
    unsubscribeOld(); // the old page is gone by the time the new one submits
    const unsubscribeNew = newPage.subscribe(() => {});
    void newPage.mutate().catch(() => undefined);
    await flush();

    const firstResponse = { ...response(), message: "from the old page" };
    const secondResponse = { ...response(), message: "from the new page" };
    if (arrivalOrder === "first-then-second") {
      first.resolve(firstResponse);
      await flush();
      second.resolve(secondResponse);
    } else {
      second.resolve(secondResponse);
      await flush();
      first.resolve(firstResponse);
    }
    await flush();
    unsubscribeNew();
    return { accept, firstResponse, secondResponse };
  }

  it("old response first, new second: seq 2 is the new page's, each written once", async () => {
    const { accept, secondResponse } = await bothSubmit("first-then-second");
    expect(accept).toHaveBeenCalledTimes(2);
    expect(store.getSnapshot().receipt?.seq).toBe(2);
    expect(store.getSnapshot().receipt?.response).toEqual(secondResponse);
  });

  it("new response first, old second: still seq 2, and the last to arrive is the one shown", async () => {
    const { accept, firstResponse } = await bothSubmit("second-then-first");
    expect(accept).toHaveBeenCalledTimes(2);
    expect(store.getSnapshot().receipt?.seq).toBe(2);
    expect(store.getSnapshot().receipt?.response).toEqual(firstResponse);
  });

  it("both requests are sent: nothing blocks, queues or de-duplicates the second submit on the client (VETO-4)", async () => {
    await bothSubmit("first-then-second");
    expect(postPlaybookEmergencyExit).toHaveBeenCalledTimes(2);
  });
});

/**
 * FE-T13(c1)-(c5) (ADR-0037 補充一 S-1, 風控 FE-R3): the 揭露地板. INV-1 -- a
 * `success` status means the response is in the store -- so that "2xx arrived, the
 * dialog closed, no banner" cannot happen. Every `mutate` is given `.catch(noop)`,
 * as `useMutation.ts:56` does.
 */
describe("FE-T13(c): a write failure ends the mutation in error; it is never swallowed", () => {
  const noop = () => undefined;

  /** Run one submit through a subscribed observer, with spies on every layer. */
  async function submit(sink: ExitReceiptSink) {
    postPlaybookEmergencyExit.mockResolvedValue(response());
    const observer = new MutationObserver(client, emergencyExitMutationOptions(client, sink));
    const unsubscribe = observer.subscribe(() => {});
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const onSettled = vi.fn();
    await observer.mutate(undefined, { onSuccess, onError, onSettled }).catch(noop);
    await flush();
    unsubscribe();
    return { observer, onSuccess, onError, onSettled };
  }

  it("(c1) a sink that throws: status error, mutate-level onSuccess 0x, onError and onSettled 1x, settle step 1x, no unhandled rejection", async () => {
    const boom = new Error("sink exploded");
    const { observer, onSuccess, onError, onSettled } = await submit({
      accept: () => {
        throw boom;
      },
    });

    expect(observer.getCurrentResult().status).toBe("error");
    expect(observer.getCurrentResult().isError).toBe(true);
    expect(observer.getCurrentResult().error).toBe(boom);
    expect(onSuccess).toHaveBeenCalledTimes(0);
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onSettled).toHaveBeenCalledTimes(1);
    // The definition-level onSettled ran exactly once: it is skipped on the success
    // path (mutation.ts:263 is never reached), and runs once on the error path.
    expect(client.cancelQueries).toHaveBeenCalledTimes(1);
    expect(client.invalidateQueries).toHaveBeenCalledTimes(1);
    expect(order).toEqual(["cancel", "invalidate"]);
  });

  it("(c2) a reducer that throws inside the real store: nothing committed, nobody notified, mutation error", async () => {
    const throwing = createExitReceiptStore({
      reducer: () => {
        throw new Error("reducer exploded");
      },
    });
    const before = throwing.getSnapshot();
    const listener = vi.fn();
    throwing.subscribe(listener);

    const { observer, onSuccess, onError } = await submit(throwing);

    expect(throwing.getSnapshot()).toBe(before);
    expect(listener).not.toHaveBeenCalled();
    expect(observer.getCurrentResult().status).toBe("error");
    expect(onSuccess).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it("(c3) a subscriber that throws: accept() returns, the receipt is in, the other subscriber runs once, the error goes to onSubscriberError, mutation success", async () => {
    const onSubscriberError = vi.fn();
    const real = createExitReceiptStore({ onSubscriberError });
    const failure = new Error("subscriber exploded");
    const first = vi.fn(() => {
      throw failure;
    });
    const second = vi.fn();
    real.subscribe(first);
    real.subscribe(second);

    const { observer, onSuccess, onError } = await submit(real);

    expect(real.getSnapshot().receipt?.seq).toBe(1);
    expect(real.getSnapshot().receipt?.response).toEqual(response());
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
    expect(onSubscriberError).toHaveBeenCalledTimes(1);
    expect(onSubscriberError).toHaveBeenCalledWith(failure);
    expect(observer.getCurrentResult().status).toBe("success");
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it("(c3b) by default a subscriber's exception is rethrown out of band, and a failing handler cannot break the loop", async () => {
    const rejections: unknown[] = [];
    const original = Promise.reject.bind(Promise);
    const spy = vi.spyOn(Promise, "reject").mockImplementation((reason?: unknown) => {
      rejections.push(reason);
      const p = original(reason);
      p.catch(() => undefined);
      return p;
    });
    try {
      const boom = new Error("subscriber exploded");
      const byDefault = createExitReceiptStore();
      byDefault.subscribe(() => {
        throw boom;
      });
      const after = vi.fn();
      byDefault.subscribe(after);
      byDefault.accept(response());
      expect(rejections).toEqual([boom]);
      expect(after).toHaveBeenCalledTimes(1);

      rejections.length = 0;
      const handlerFailure = new Error("handler exploded");
      const withBadHandler = createExitReceiptStore({
        onSubscriberError: () => {
          throw handlerFailure;
        },
      });
      withBadHandler.subscribe(() => {
        throw boom;
      });
      const stillRuns = vi.fn();
      withBadHandler.subscribe(stillRuns);
      expect(() => withBadHandler.accept(response())).not.toThrow();
      expect(stillRuns).toHaveBeenCalledTimes(1);
      expect(rejections).toEqual([handlerFailure]);
    } finally {
      spy.mockRestore();
    }
  });

  it("(c4) INV-1 matrix: each scenario ends in its expected status; a success always has the receipt, an error never has half of one", async () => {
    const failure = new Error("injected");
    type Scenario = {
      name: string;
      sink: () => ExitReceiptStore | ExitReceiptSink;
      request: "ok" | "reject";
      /** Written down per scenario, so a scenario that silently changes outcome fails here. */
      expectedStatus: "success" | "error";
    };
    const scenarios: Scenario[] = [
      { name: "normal", sink: () => createExitReceiptStore(), request: "ok", expectedStatus: "success" },
      {
        name: "c1 sink throws",
        sink: () => ({ accept: () => { throw failure; } }),
        request: "ok",
        expectedStatus: "error",
      },
      {
        name: "c2 reducer throws",
        sink: () => createExitReceiptStore({ reducer: () => { throw failure; } }),
        request: "ok",
        expectedStatus: "error",
      },
      {
        name: "c3 subscriber throws",
        sink: () => {
          const s = createExitReceiptStore({ onSubscriberError: () => undefined });
          s.subscribe(() => { throw failure; });
          return s;
        },
        request: "ok",
        expectedStatus: "success",
      },
      {
        name: "mutationFn rejects",
        sink: () => createExitReceiptStore(),
        request: "reject",
        expectedStatus: "error",
      },
    ];

    for (const scenario of scenarios) {
      postPlaybookEmergencyExit.mockReset();
      if (scenario.request === "ok") postPlaybookEmergencyExit.mockResolvedValue(response());
      else postPlaybookEmergencyExit.mockRejectedValue(new ApiError("server error", 500));
      const sink = scenario.sink();
      const seqBefore = "getSnapshot" in sink ? (sink.getSnapshot().receipt?.seq ?? 0) : 0;
      const observer = new MutationObserver(client, emergencyExitMutationOptions(client, sink));
      await observer.mutate().catch(noop);
      await flush();
      const result = observer.getCurrentResult();
      const seqAfter = "getSnapshot" in sink ? (sink.getSnapshot().receipt?.seq ?? 0) : 0;

      expect(result.status, scenario.name).toBe(scenario.expectedStatus);
      if (scenario.expectedStatus === "success") {
        // INV-1: success means the response is in the store.
        expect(seqAfter, scenario.name).toBe(seqBefore + 1);
        expect((sink as ExitReceiptStore).getSnapshot().receipt?.response, scenario.name).toEqual(response());
      } else {
        // The dialog shows NB-6 from `isError`; the Step-3 condition itself
        // (`isError && step === "final"`) is pinned verbatim in exitFlowStructure.
        expect(result.isError, scenario.name).toBe(true);
        // ... and an error never leaves a half-written receipt behind.
        expect(seqAfter, scenario.name).toBe(seqBefore);
      }
    }
  });

  it("(c4b) the reducer under test really is the default one when none is injected", () => {
    const store = createExitReceiptStore();
    expect(store.getSnapshot()).toBe(INITIAL_EXIT_RECEIPT_STATE);
    store.accept(response());
    expect(store.getSnapshot()).toEqual(exitReceiptReducer(INITIAL_EXIT_RECEIPT_STATE, { type: "accepted", response: response() }));
  });
});
