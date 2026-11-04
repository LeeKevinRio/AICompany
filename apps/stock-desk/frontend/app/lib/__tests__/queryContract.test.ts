/**
 * Library-contract tests for the TanStack Query v5 semantics the exit-feedback
 * screen relies on (tech-architect Q14 FE-T6). They drive `QueryClient` and
 * `QueryObserver` directly — no React — so they run in the node environment.
 *
 * They are the tripwire for a package upgrade: the page's guarantees (the
 * status bar unmounts when a refetch fails; AC-55's cancel-then-invalidate
 * remedy; the staleness clock behind R-4) are read-from-source facts about
 * `@tanstack/query-core` 5.101.4, not documented API. If one of these tests
 * fails after a bump, the page logic that cites it needs re-reading.
 */

import { QueryClient, QueryObserver } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const KEY = ["playbook-today"];

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

/** Let TanStack's `setTimeout(0)`-batched notifications and microtasks settle. */
async function settle(): Promise<void> {
  await vi.advanceTimersByTimeAsync(0);
}

let client: QueryClient;

beforeEach(() => {
  vi.useFakeTimers();
  client = new QueryClient();
});

afterEach(() => {
  client.clear();
  vi.useRealTimers();
});

describe("(a) a failed background refetch drops isSuccess but keeps the data", () => {
  it("isSuccess stays true while the retry waits, then flips to false with data intact", async () => {
    let call = 0;
    const observer = new QueryObserver<string>(client, {
      queryKey: KEY,
      queryFn: () => {
        call += 1;
        return call === 1 ? Promise.resolve("v1") : Promise.reject(new Error("boom"));
      },
      retry: 1,
      retryDelay: 1000,
    });
    const unsubscribe = observer.subscribe(() => {});
    await settle();
    expect(observer.getCurrentResult().isSuccess).toBe(true);

    void observer.refetch();
    await settle(); // first attempt of the refetch failed; the retry is waiting
    const waiting = observer.getCurrentResult();
    expect(call).toBe(2);
    expect(waiting.isSuccess).toBe(true); // `failed` only bumps the failure count
    expect(waiting.isRefetchError).toBe(false);

    await vi.advanceTimersByTimeAsync(1000); // the retry fails too
    const failed = observer.getCurrentResult();
    expect(call).toBe(3);
    expect(failed.isSuccess).toBe(false);
    expect(failed.isError).toBe(true);
    expect(failed.isRefetchError).toBe(true);
    expect(failed.data).toBe("v1"); // the stale value is still there, and must not be used
    unsubscribe();
  });
});

describe("(b)(c) invalidateQueries cancels an in-flight request only when the query has data", () => {
  it("(b) with data: the superseded request's late answer is discarded", async () => {
    const calls: Array<Deferred<string>> = [];
    const queryFn = vi.fn(() => {
      const d = deferred<string>();
      calls.push(d);
      return d.promise;
    });
    const observer = new QueryObserver<string>(client, { queryKey: KEY, queryFn });
    const unsubscribe = observer.subscribe(() => {});
    calls[0]?.resolve("v1");
    await settle();
    expect(observer.getCurrentResult().data).toBe("v1");

    void observer.refetch(); // request #2 in flight (e.g. the focus refetch)
    await settle();
    void client.invalidateQueries({ queryKey: KEY }); // cancels #2, starts #3
    await settle();
    expect(queryFn).toHaveBeenCalledTimes(3);

    calls[2]?.resolve("fresh");
    await settle();
    calls[1]?.resolve("stale-late"); // the cancelled request answers last
    await settle();
    expect(observer.getCurrentResult().data).toBe("fresh");
    unsubscribe();
  });

  it("(c) without data: it folds into the request in flight, so a pre-exit answer is applied (the AC-55 gap)", async () => {
    const calls: Array<Deferred<string>> = [];
    const queryFn = vi.fn(() => {
      const d = deferred<string>();
      calls.push(d);
      return d.promise;
    });
    const observer = new QueryObserver<string>(client, { queryKey: KEY, queryFn });
    const unsubscribe = observer.subscribe(() => {});
    await settle();
    expect(observer.getCurrentResult().isPending).toBe(true);

    void client.invalidateQueries({ queryKey: KEY });
    await settle();
    // No second request: invalidate alone cannot replace the pre-exit GET.
    expect(queryFn).toHaveBeenCalledTimes(1);

    calls[0]?.resolve("pre-exit");
    await settle();
    expect(observer.getCurrentResult().data).toBe("pre-exit");
    unsubscribe();
  });
});

describe("(d) cancelQueries then invalidateQueries closes the gap without an error flash", () => {
  it("drops the pre-exit answer, starts a new request, and the status never leaves pending", async () => {
    const calls: Array<Deferred<string>> = [];
    const queryFn = vi.fn(() => {
      const d = deferred<string>();
      calls.push(d);
      return d.promise;
    });
    const observer = new QueryObserver<string>(client, { queryKey: KEY, queryFn });
    const statuses: string[] = [];
    const unsubscribe = observer.subscribe((result) => statuses.push(result.status));
    await settle();

    // Exactly what `emergencyExitMutationOptions().onSettled` does.
    void client.cancelQueries({ queryKey: KEY });
    void client.invalidateQueries({ queryKey: KEY });
    await settle();

    expect(queryFn).toHaveBeenCalledTimes(2);
    expect(observer.getCurrentResult().status).toBe("pending");
    expect(observer.getCurrentResult().isError).toBe(false);

    calls[0]?.resolve("pre-exit"); // the stale GET answers late: dropped
    await settle();
    expect(observer.getCurrentResult().isPending).toBe(true);
    expect(observer.getCurrentResult().data).toBeUndefined();

    calls[1]?.resolve("post-exit");
    await settle();
    expect(observer.getCurrentResult().data).toBe("post-exit");
    expect(statuses).not.toContain("error");
    unsubscribe();
  });
});

describe("(e) dataUpdatedAt is the clock R-4 measures", () => {
  it("advances on a successful refetch with identical content, and does not move on error", async () => {
    vi.setSystemTime(new Date("2026-08-11T01:00:00Z"));
    let fail = false;
    const observer = new QueryObserver<{ checks: string[] }>(client, {
      queryKey: KEY,
      queryFn: () =>
        fail ? Promise.reject(new Error("boom")) : Promise.resolve({ checks: ["same"] }),
      retry: false,
    });
    const unsubscribe = observer.subscribe(() => {});
    await settle();
    const first = observer.getCurrentResult().dataUpdatedAt;
    expect(first).toBe(new Date("2026-08-11T01:00:00Z").getTime());

    vi.setSystemTime(new Date("2026-08-11T05:00:00Z"));
    await observer.refetch();
    const second = observer.getCurrentResult().dataUpdatedAt;
    expect(second).toBe(new Date("2026-08-11T05:00:00Z").getTime()); // same content, newer time

    fail = true;
    vi.setSystemTime(new Date("2026-08-11T09:00:00Z"));
    await observer.refetch();
    const failed = observer.getCurrentResult();
    expect(failed.isError).toBe(true);
    expect(failed.dataUpdatedAt).toBe(second); // an error leaves the acquisition time alone
    unsubscribe();
  });
});
