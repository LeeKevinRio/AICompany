import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EmptyPositionsState } from "../../components/EmptyPositionsState";
import { DisclosureSection } from "../../positions/DisclosureSection";
import { InventoryListSkeleton } from "../../positions/InventoryList";
import { InventoryRowView, InventoryTableHeader } from "../../positions/InventoryRowView";
import type { InventoryRowViewProps } from "../../positions/InventoryRowView";
import { ApiError } from "../api";
import type { Position } from "../types";

const APP_DIR = fileURLToPath(new URL("../../", import.meta.url));

function read(rel: string): string {
  return readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8");
}

function makePosition(overrides: Partial<Position> = {}): Position {
  return {
    id: 7,
    symbol: "2330",
    market: "TW",
    quantity: "1000",
    avg_cost: "605.5",
    currency: "TWD",
    opened_at: null,
    instrument_type: "stock",
    sector: null,
    note: "long term",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    ...overrides,
  };
}

function renderRow(overrides: Partial<InventoryRowViewProps> = {}, position = makePosition()): string {
  return renderToStaticMarkup(
    createElement(InventoryRowView, {
      position,
      name: "台積電",
      highlighted: false,
      mode: "display",
      draft: { quantity: position.quantity, avg_cost: position.avg_cost, note: position.note ?? "" },
      onDraftChange: () => {},
      saveError: null,
      saving: false,
      pendingDeleteId: null,
      onEdit: () => {},
      onSave: () => {},
      onCancel: () => {},
      onMore: () => {},
      onRemove: () => {},
      ...overrides,
    }),
  );
}

describe("AC-2 / AC-3 display mode row", () => {
  const html = renderRow();

  it("shows symbol link to the stock page, name, market, currency, quantity, average cost and note", () => {
    expect(html).toContain('href="/position/2330?market=TW"');
    expect(html).toContain("台積電");
    expect(html).toContain("台股");
    expect(html).toContain("TWD");
    expect(html).toContain("1,000");
    expect(html).toContain("NT$605.50");
    expect(html).toContain("long term");
  });

  it("S20 / S4 / S6: 修改 and 移除 buttons carry the symbol-qualified names and visible text", () => {
    expect(html).toContain('aria-label="修改 2330 持倉"');
    expect(html).toContain('aria-label="移除 2330 持倉"');
    expect(html).toMatch(/>修改<\/button>/);
    expect(html).toMatch(/>移除<\/button>/);
    expect(html).toContain('id="pos-edit-7"');
  });

  it("is anchored as #pos-{id}, focusable by script, with the scroll offset", () => {
    expect(html).toContain('id="pos-7"');
    expect(html).toContain('tabindex="-1"');
    expect(html).toContain("scroll-mt-4");
  });

  it("no inputs in display mode, no edit-only buttons", () => {
    expect(html).not.toContain("<input");
    expect(html).not.toMatch(/>儲存<\/button>/);
    expect(html).not.toMatch(/>更多<\/button>/);
  });

  it("buttons are at least 44px tall with a focus-visible ring and the red 移除 style has text (not colour only)", () => {
    expect(html.match(/min-h-11/g)?.length).toBeGreaterThanOrEqual(3);
    expect(html).toContain("focus-visible:outline-sky-400");
    expect(html).toContain("border-red-900");
    expect(html).toContain("gap-3");
  });

  it("an unknown name prints nothing: no undefined, no empty parentheses, no symbol repeated as a name", () => {
    const noName = renderRow({ name: undefined });
    expect(noName).not.toContain("undefined");
    expect(noName).not.toContain("()");
    expect(noName).not.toContain("（）");
    expect(noName).not.toContain("truncate text-xs");
  });

  it("D-8: an empty, whitespace or null note is shown as an em dash", () => {
    for (const note of [null, "", "   "]) {
      const row = renderRow({}, makePosition({ note }));
      expect(row).toContain("—");
      expect(row).not.toContain("long term");
    }
  });

  it("highlight (hash target) marks the row; a plain row does not", () => {
    expect(renderRow({ highlighted: true })).toContain("border-l-neutral-100 bg-neutral-900/40");
    expect(html).toContain("border-l-transparent");
  });

  it("market and currency stay in the markup for both widths (same information at 375 and 1280)", () => {
    expect(html).toContain("lg:hidden");
    expect(html).toContain("hidden min-w-0");
    expect(html).toContain("lg:block");
  });
});

describe("AC-3 edit mode row", () => {
  const html = renderRow({ mode: "edit" });

  it("only quantity, average cost and note are inputs; symbol, market, currency stay text", () => {
    expect(html.match(/<input/g)).toHaveLength(3);
    expect(html).toContain('id="pos-7-quantity"');
    expect(html).toContain('id="pos-7-avg_cost"');
    expect(html).toContain('id="pos-7-note"');
    expect(html).not.toContain('id="pos-7-symbol"');
    expect(html).not.toContain("<select");
  });

  it("S20: input names are symbol-qualified; values are pre-filled", () => {
    expect(html).toContain('aria-label="2330 數量"');
    expect(html).toContain('aria-label="2330 平均成本（原幣）"');
    expect(html).toContain('aria-label="2330 備註"');
    expect(html).toContain('value="1000"');
    expect(html).toContain('value="605.5"');
    expect(html).toContain('value="long term"');
  });

  it("S5: 儲存 / 取消 / 更多 with the 更多 accessible name from S20", () => {
    expect(html).toMatch(/>儲存<\/button>/);
    expect(html).toMatch(/>取消<\/button>/);
    expect(html).toMatch(/>更多<\/button>/);
    expect(html).toContain('aria-label="更多：修改 2330 的其他欄位"');
    expect(html).not.toMatch(/>修改<\/button>/);
  });

  it("numeric inputs use the decimal keyboard; inputs are 16px on mobile and 44px tall", () => {
    expect(html.match(/inputMode="decimal"|inputmode="decimal"/gi)).toHaveLength(2);
    expect(html).toContain("text-base");
    expect(html).toContain("lg:text-sm");
    expect(html).toContain("min-h-11");
  });

  it("labels are visible below lg and screen-reader-only from lg", () => {
    expect(html).toContain("block text-xs text-neutral-400 lg:sr-only");
  });

  it("the editing row carries the same mark as a hash target", () => {
    expect(html).toContain("border-l-neutral-100 bg-neutral-900/40");
  });

  it("D6: no 已儲存 anywhere", () => {
    expect(html).not.toContain("已儲存");
  });

  it("a reserved hint slot sits under each input (no layout shift when a message appears)", () => {
    expect(html.match(/mt-1 min-h-4/g)).toHaveLength(3);
  });
});

describe("AC-3 saving state (V1)", () => {
  const html = renderRow({ mode: "edit", saving: true });

  it("inputs and every button are disabled and the primary shows 儲存中…", () => {
    expect(html.match(/<input[^>]*disabled=""/g)).toHaveLength(3);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>儲存中…<\/button>/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>取消<\/button>/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>更多<\/button>/);
  });
});

describe("AC-3 failed save stays in edit mode and shows backend text", () => {
  it("field errors appear under their inputs verbatim, red border, inputs keep their values", () => {
    const error = new ApiError("請求失敗（HTTP 422）", 422, { quantity: "數量必須大於 0" });
    const html = renderRow({
      mode: "edit",
      saveError: error,
      draft: { quantity: "0", avg_cost: "605.5", note: "long term" },
    });
    expect(html).toContain("數量必須大於 0");
    expect(html).toContain('value="0"');
    expect(html).toContain("border-red-900");
    expect(html).toContain('aria-invalid="true"');
    expect(html).toMatch(/>儲存<\/button>/);
    expect(html).not.toContain("儲存失敗");
  });

  it("field error text is an alert linked to its input via aria-describedby; no error means no alert role", () => {
    const withError = renderRow({
      mode: "edit",
      saveError: new ApiError("x", 422, { quantity: "數量必須大於 0" }),
    });
    expect(withError).toMatch(/<p id="pos-7-quantity-hint" role="alert"[^>]*>數量必須大於 0<\/p>/);
    expect(withError).toContain('aria-describedby="pos-7-quantity-hint"');
    expect(renderRow({ mode: "edit" })).not.toContain('role="alert"');
  });

  it("row-level error area is a cell inside the row", () => {
    const html = renderRow({ mode: "edit", saveError: new ApiError("找不到指定的部位", 404) });
    expect(html).toMatch(/<div role="cell" class="col-span-2 space-y-2[^"]*"><p role="alert"/);
  });

  it("a non-field error shows ErrorPanel as 儲存失敗：原因 with role=alert, and stays editable", () => {
    const html = renderRow({
      mode: "edit",
      saveError: new ApiError("找不到指定的部位", 404),
    });
    expect(html).toContain('role="alert"');
    expect(html).toContain("儲存失敗：找不到指定的部位");
    expect(html.match(/<input/g)).toHaveLength(3);
  });

  it("C8: a field error with no input (body / currency) goes to ErrorPanel, not dropped", () => {
    const html = renderRow({
      mode: "edit",
      saveError: new ApiError("x", 422, { body: "至少需提供一個欄位", currency: "幣別不符" }),
    });
    expect(html).toContain("儲存失敗：至少需提供一個欄位");
    expect(html).toContain("儲存失敗：幣別不符");
  });
});

describe("AC-5 removal button states (V2)", () => {
  it("shows 移除中… on the pending row and disables every row's 移除", () => {
    const pending = renderRow({ pendingDeleteId: 7 });
    expect(pending).toMatch(/<button[^>]*disabled=""[^>]*>移除中…<\/button>/);
    expect(pending).toMatch(/<button[^>]*disabled=""[^>]*>修改<\/button>/);
    expect(pending).toContain("opacity-60");
    const other = renderRow({ pendingDeleteId: 99 });
    expect(other).toMatch(/<button[^>]*disabled=""[^>]*>移除<\/button>/);
    expect(other).toMatch(/<button[^>]*>修改<\/button>/);
    expect(other).not.toMatch(/<button[^>]*disabled=""[^>]*>修改<\/button>/);
  });
});

describe("focus after a failed save / remove (qa-reviewer medium)", () => {
  const row = read("../../positions/InventoryRow.tsx");
  const page = read("../../positions/page.tsx");

  it("ids used for focus exist on the markup", () => {
    const edit = renderRow({ mode: "edit" });
    expect(edit).toContain('id="pos-save-7"');
    const display = renderRow();
    expect(display).toContain('id="pos-remove-7"');
  });

  it("a failed PATCH moves focus (after the controls are enabled again) to the first errored field, else 儲存", () => {
    expect(row).toContain('patch.status !== "error"');
    expect(row).toContain("saveErrorFocusTarget(patch.error)");
    expect(row).toContain("positionSaveButtonId(position.id)");
    expect(row).toContain(".focus()");
  });

  it("a failed remove returns focus to that row's 移除 button once re-enabled", () => {
    expect(page).toContain("pendingRemoveFailureFocus.current = position.id");
    expect(page).toContain("positionRemoveButtonId(id)");
    expect(page).toContain("pendingDeleteId !== null");
  });

  it("the already-gone notice uses a neutral tone, success messages stay emerald", () => {
    expect(page).toContain('tone: "neutral"');
    expect(page).toContain("border-neutral-800 bg-neutral-900/40 text-neutral-300");
    expect(page).toContain("border-emerald-900 bg-emerald-950/40 text-emerald-300");
  });
});

describe("table header and skeleton", () => {
  it("desktop header uses the existing column labels, no sort buttons, an sr-only actions column", () => {
    const html = renderToStaticMarkup(createElement(InventoryTableHeader));
    for (const label of ["代號", "市場", "數量", "平均成本（原幣）", "備註"]) {
      expect(html).toContain(`>${label}<`);
    }
    expect(html).toContain("sr-only");
    expect(html).not.toContain("<button");
    expect(html).toContain("hidden");
    expect(html).toContain("lg:block");
  });

  it("the six-column template matches the visual spec (208px actions, breakpoint lg)", () => {
    const src = read("../../positions/InventoryRowView.tsx");
    expect(src).toContain(
      "lg:grid-cols-[minmax(150px,1.3fr)_minmax(90px,0.7fr)_minmax(110px,1fr)_minmax(130px,1fr)_minmax(140px,1.4fr)_208px]",
    );
    expect(src).not.toContain("md:grid-cols");
  });

  it("skeleton: header + three h-16 rows from lg, three h-32 cards below", () => {
    const html = renderToStaticMarkup(createElement(InventoryListSkeleton));
    expect(html.match(/h-16/g)).toHaveLength(3);
    expect(html.match(/h-32/g)).toHaveLength(3);
    expect(html).toContain("h-10");
  });

  it("no horizontal scroll helpers in the inventory sources", () => {
    for (const rel of ["InventoryRowView.tsx", "InventoryList.tsx", "page.tsx"]) {
      const src = read(`../../positions/${rel}`);
      expect(src, rel).not.toContain("overflow-x-auto");
      expect(src, rel).not.toMatch(/min-w-\[\d{3,}px\]/);
    }
  });
});

describe("AC-6 / AC-7 collapsible sections", () => {
  function section(open: boolean): string {
    return renderToStaticMarkup(
      createElement(DisclosureSection, {
        id: "inventory-csv",
        title: "CSV 匯入",
        open,
        onToggle: () => {},
        children: createElement("p", null, "content"),
      }),
    );
  }

  it("collapsed: aria-expanded=false, controls resolve, content hidden but present", () => {
    const html = section(false);
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('aria-controls="inventory-csv-content"');
    expect(html).toMatch(/id="inventory-csv-content"[^>]*hidden/);
    expect(html).toContain("content");
  });

  it("expanded: aria-expanded=true and content visible", () => {
    const html = section(true);
    expect(html).toContain('aria-expanded="true"');
    expect(html).not.toMatch(/id="inventory-csv-content"[^>]*hidden/);
  });

  it("S20: toggle name is 展開／收合 + title, button is a real button inside the heading, 44px, focus ring", () => {
    const html = section(false);
    expect(html).toContain('aria-label="展開／收合 CSV 匯入"');
    expect(html).toMatch(/<h2><button type="button"/);
    expect(html).toContain("min-h-11");
    expect(html).toContain("focus-visible:outline-sky-400");
    expect(html).toContain("motion-reduce:transition-none");
    expect(html).not.toContain("transition-all");
  });
});

describe("AC-1 / S17 / S18 empty state", () => {
  it("home variant: one line plus a 新增持倉 button to /positions; old copy gone", () => {
    const html = renderToStaticMarkup(createElement(EmptyPositionsState));
    expect(html).toContain("尚無持倉");
    expect(html).toContain('href="/positions"');
    expect(html).toContain(">新增持倉<");
    expect(html).not.toContain("目前尚無任何持倉");
    expect(html).not.toContain("前往匯入 CSV");
    expect(html).not.toContain("匯入 CSV 檔案，或手動新增");
  });

  it("inventory variant: the line only, no button", () => {
    const html = renderToStaticMarkup(createElement(EmptyPositionsState, { withAddLink: false }));
    expect(html).toContain("尚無持倉");
    expect(html).not.toContain("<a");
  });
});

describe("page structure (AC-2, AC-6, AC-7, AC-8, AC-10)", () => {
  const page = read("../../positions/page.tsx");

  it("uses the 5xl container and the list comes before the add and CSV sections", () => {
    expect(page).toContain("mx-auto max-w-5xl px-4 py-8");
    const list = page.indexOf("<InventoryList");
    const add = page.indexOf("<ManualAddForm");
    const csv = page.indexOf("<ImportCsvSection");
    expect(list).toBeGreaterThan(-1);
    expect(add).toBeGreaterThan(list);
    expect(csv).toBeGreaterThan(add);
  });

  it("data comes from GET /api/positions only: no quote, FX or health dependency", () => {
    expect(page).toContain("usePositions(true)");
    for (const dep of ["usePortfolioSummary", "useHealth", "usePortfolioLimits"]) {
      expect(page).not.toContain(dep);
    }
  });

  it("add section follows the inventory (collapsed with rows, expanded when empty); CSV starts collapsed", () => {
    expect(page).toContain("items !== undefined && items.length === 0");
    expect(page).toContain("useState(false)");
  });

  it("header 新增 expands, scrolls and focuses the symbol input", () => {
    expect(page).toContain("scrollIntoView");
    expect(page).toContain('"symbol"');
    expect(page).toContain("INVENTORY_ADD_BUTTON");
  });

  it("states: skeleton, ErrorPanel + retry, empty line", () => {
    expect(page).toContain("<InventoryListSkeleton");
    expect(page).toContain("LIST_LOAD_FAILED_LABEL");
    expect(page).toContain("LIST_RETRY_LABEL");
    expect(page).toContain("<EmptyPositionsState withAddLink={false}");
    expect(page).toContain("REMOVE_FAILED_LABEL");
  });

  it("status message is a role=status live region and only add / remove write to it", () => {
    expect(page).toContain('role="status"');
    expect(page).toContain("buildAddedToast");
    expect(page).toContain("buildRemovedToast");
    expect(page).toContain("REMOVED_ALREADY_GONE");
    expect(page).not.toContain("已儲存");
  });

  it("remove asks for confirmation using the wording constants and the list's quantity formatter", () => {
    expect(page).toContain("window.confirm(");
    expect(page).toContain("buildRemoveConfirmSentence(position.symbol, formatQuantity(position.quantity))");
  });

  it("the hash is handled only after the list loaded, once per hash value", () => {
    expect(page).toContain("if (items === undefined) return;");
    expect(page).toContain("parsePositionAnchor(hash)");
    expect(page).toContain("handledHash.current === hash");
  });

  it("the heading can take focus (empty list after a removal)", () => {
    expect(page).toContain("tabIndex={-1}");
    expect(page).toContain("headingRef");
  });

  it("no explanatory paragraph survives (PRD FR-10)", () => {
    for (const rel of ["page.tsx", "ImportCsvSection.tsx", "ManualAddForm.tsx", "InventoryRowView.tsx"]) {
      const src = read(`../../positions/${rel}`);
      expect(src, rel).not.toContain("以 CSV 批次匯入既有部位");
      expect(src, rel).not.toContain("下載範本並依格式填寫後上傳");
      expect(src, rel).not.toContain("匯入 / 新增部位");
      expect(src, rel).not.toContain("手動新增部位");
      expect(src, rel).not.toContain("回總覽</Link>");
    }
  });

  it("S14 / AC-6: ManualAddForm keeps its fields and reports success through a callback instead of an inline box", () => {
    const form = read("../../positions/ManualAddForm.tsx");
    expect(form).toContain("onSuccess?.(created.symbol)");
    expect(form).not.toContain("已新增部位");
    expect(form).not.toContain("<h2");
    expect(form).toContain("ADD_SUBMIT_LABEL");
    expect(form).toContain("SECTOR_SOURCE_DISCLOSURE");
    expect(form).toContain("SECTOR_US_DISABLED_HINT");
  });

  it("FR-7: ImportCsvSection keeps the template link, error table and the 回總覽查看 link", () => {
    const csv = read("../../positions/ImportCsvSection.tsx");
    expect(csv).toContain("下載 CSV 範本");
    expect(csv).toContain("匯入錯誤明細");
    expect(csv).toContain("回總覽查看");
    expect(csv).toContain("成功匯入");
    expect(csv).not.toContain("<h2");
  });
});

describe("C1: inline save only calls PATCH, never the PUT path", () => {
  const row = read("../../positions/InventoryRow.tsx");

  it("InventoryRow saves through usePatchPosition and never touches updatePosition / useUpdatePosition", () => {
    expect(row).toContain("usePatchPosition()");
    expect(row).toContain("buildPositionPatch(position, draft)");
    expect(row).not.toContain("useUpdatePosition");
    expect(row).not.toContain("updatePosition");
  });

  it("an unchanged draft sends nothing", () => {
    expect(row).toContain("isEmptyPatch(input)");
  });

  it("failed saves never leave edit mode: setMode(\"display\") happens only in onSuccess, cancel and the no-change path", () => {
    const calls = row.match(/setMode\("display"\)/g) ?? [];
    expect(calls).toHaveLength(2); // leaveEditMode() and onSuccess
    expect(row).toContain("onSuccess: () => {");
    expect(row).not.toContain("onError");
    expect(row).not.toContain("onSettled");
  });

  it("api.patchPosition issues PATCH on /api/positions/{id} with a JSON body", () => {
    const api = read("../api.ts");
    const start = api.indexOf("export function patchPosition");
    const body = api.slice(start, api.indexOf("export function deletePosition"));
    expect(body).toContain('method: "PATCH"');
    expect(body).toContain("`/api/positions/${id}`");
    expect(body).toContain("JSON.stringify(input)");
  });

  it("Enter is guarded at the handler (re-entry) and Esc/Enter go through inlineKeyAction", () => {
    expect(row).toContain("shouldBlockPositionSubmit(patch.isPending)");
    const view = read("../../positions/InventoryRowView.tsx");
    expect(view).toContain("inlineKeyAction(");
    expect(view).toContain("event.nativeEvent.isComposing");
    expect(view.match(/onKeyDown=\{handleInputKeyDown\}/g)).toHaveLength(3);
  });
});

describe("mutation invalidation (tech-architect: positions, summary, limits, advice, leverage)", () => {
  const queries = read("../queries.ts");

  it("every position mutation invalidates all five prefixes through one helper", () => {
    const start = queries.indexOf("export const POSITION_DEPENDENT_QUERY_KEYS");
    const keys = queries.slice(start, queries.indexOf("] as const", start));
    for (const key of ["positions", "portfolio-summary", "portfolio-limits", "advice", "leverage"]) {
      expect(keys, key).toContain(`"${key}"`);
    }
    for (const hook of [
      "useCreatePosition",
      "useUpdatePosition",
      "usePatchPosition",
      "useDeletePosition",
      "useImportPositionsCsv",
    ]) {
      const start = queries.indexOf(`export function ${hook}`);
      expect(start, hook).toBeGreaterThan(-1);
      const end = queries.indexOf("\nexport function", start + 10);
      expect(queries.slice(start, end), hook).toContain("invalidatePositionQueries(queryClient)");
    }
  });

  it("a 404 on remove re-fetches the list", () => {
    const start = queries.indexOf("export function useDeletePosition");
    const body = queries.slice(start, queries.indexOf("\nexport function", start + 10));
    expect(body).toContain("error.status === 404");
  });
});

describe("EditPositionModal prop type covers both sources", () => {
  it("takes EditablePosition, not the valuation-carrying summary shape", () => {
    const modal = read("../../components/EditPositionModal.tsx");
    expect(modal).toContain("position: EditablePosition;");
    expect(modal).not.toContain("SummaryPositionItem");
  });
});

describe("C5: no navigation to /positions/import outside next.config.ts", () => {
  function sourceFiles(dir: string): string[] {
    const out: string[] = [];
    for (const entry of readdirSync(dir)) {
      if (entry === "__tests__" || entry === "node_modules") continue;
      const full = `${dir}${entry}`;
      if (statSync(full).isDirectory()) out.push(...sourceFiles(`${full}/`));
      else if (/\.(ts|tsx)$/.test(entry)) out.push(full);
    }
    return out;
  }

  it("no app source (tests excluded) mentions the old route; the backend /api/positions/import endpoint is the only look-alike", () => {
    const offenders = sourceFiles(APP_DIR).filter((file) =>
      /(?<!\/api)\/positions\/import/.test(readFileSync(file, "utf-8")),
    );
    expect(offenders).toEqual([]);
  });

  it("README points at /positions", () => {
    const readme = readFileSync(fileURLToPath(new URL("../../../README.md", import.meta.url)), "utf-8");
    expect(readme).toContain("`/positions`");
    expect(readme).not.toContain("匯入 / 新增部位");
  });

  it("the old page file is gone and the moved components live under app/positions/", () => {
    expect(existsSync(`${APP_DIR}positions/import/page.tsx`)).toBe(false);
    expect(existsSync(`${APP_DIR}positions/import`)).toBe(false);
    expect(existsSync(`${APP_DIR}positions/page.tsx`)).toBe(true);
    expect(existsSync(`${APP_DIR}positions/ManualAddForm.tsx`)).toBe(true);
    expect(existsSync(`${APP_DIR}positions/ImportCsvSection.tsx`)).toBe(true);
  });
});
