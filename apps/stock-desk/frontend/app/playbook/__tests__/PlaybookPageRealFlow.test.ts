/**
 * FE-T4, second half (ADR-0037): the page with the *real* `useEmergencyExitFlow`,
 * the real QueryClient and the real Providers-scope store, in the four `/today`
 * states. `PlaybookPageStates.test.ts` swaps the flow hook out so it can inject a
 * receipt; this file proves the unswapped wiring (store context, sink into the
 * mutation, `useSyncExternalStore` with the server snapshot) renders each state
 * and, with an empty store, shows no banner anywhere.
 *
 * (A receipt seeded into the store cannot show in static markup: the server
 * snapshot is always the empty initial state by design, FE-C1. The banner-with-a-
 * receipt half is therefore asserted in `PlaybookPageStates.test.ts`.)
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ApiError } from "../../lib/api";
import { ExitReceiptStoreContext, ExitReceiptStoreProvider } from "../../lib/exitReceiptContext";
import { createExitReceiptStore } from "../../lib/exitReceiptStore";
import type { PlaybookTodayResponse } from "../../lib/types";
import PlaybookPage from "../page";
import { receiptResponse, todayResponse } from "./pageFixtures";

type State = "pending" | "error-no-data" | "error-with-data" | "success";

function render(state: State, tree: "provider" | "seeded-store"): string {
  const client = new QueryClient({ defaultOptions: { queries: { retryOnMount: false } } });
  const key = ["playbook-today"];
  if (state === "success") {
    client.setQueryData(key, todayResponse());
  } else if (state !== "pending") {
    client
      .getQueryCache()
      .build<PlaybookTodayResponse, Error, PlaybookTodayResponse>(client, {
        queryKey: key,
        queryFn: () => Promise.reject(new Error("unused")),
      })
      .setState({
        status: "error",
        fetchStatus: "idle",
        error: new ApiError("boom", 500),
        errorUpdatedAt: Date.now(),
        ...(state === "error-with-data" ? { data: todayResponse(), dataUpdatedAt: Date.now() - 1 } : {}),
      });
  }
  const page = createElement(PlaybookPage);
  if (tree === "provider") {
    return renderToStaticMarkup(
      createElement(QueryClientProvider, { client }, createElement(ExitReceiptStoreProvider, null, page)),
    );
  }
  const store = createExitReceiptStore();
  store.accept(receiptResponse());
  return renderToStaticMarkup(
    createElement(
      QueryClientProvider,
      { client },
      createElement(ExitReceiptStoreContext.Provider, { value: store }, page),
    ),
  );
}

describe.each(["pending", "error-no-data", "error-with-data", "success"] as const)(
  "PlaybookPage with the real flow, /today = %s",
  (state) => {
    it("renders one trigger and one empty role=status container when the store is empty", () => {
      const markup = render(state, "provider");
      expect(markup.split("全部出清</button>")).toHaveLength(2);
      const main = markup.slice(markup.indexOf("<main"), markup.indexOf("</main>"));
      expect(main.split('role="status"')).toHaveLength(2);
      expect(main).toMatch(/<\/div><div role="status"><\/div>/);
    });

    it("server-renders the empty state even when the store already holds a receipt (hydration-safe, FE-C1)", () => {
      expect(render(state, "seeded-store")).toBe(render(state, "provider"));
    });
  },
);

describe("the page cannot render without the store provider", () => {
  it("throws a clear error instead of silently using a module-level store", () => {
    const client = new QueryClient();
    expect(() =>
      renderToStaticMarkup(createElement(QueryClientProvider, { client }, createElement(PlaybookPage))),
    ).toThrow(/ExitReceiptStoreProvider/);
  });
});
