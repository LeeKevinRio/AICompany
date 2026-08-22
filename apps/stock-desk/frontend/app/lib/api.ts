import type {
  AdviceResponse,
  AlertEvaluationResponse,
  AlertEvent,
  AlertEventListResponse,
  AlertRule,
  AlertRuleInput,
  AlertRuleListResponse,
  AlertRulePatch,
  AppSettingsPatch,
  BacktestRequest,
  BacktestResponse,
  BarsResponse,
  CreatePositionInput,
  DirectoryItem,
  DirectorySearchResponse,
  HealthResponse,
  ImportPositionsResponse,
  KellyGateReasonCode,
  KellyImportRefusal,
  KellyInputDisclosuresView,
  KellyInputListView,
  KellyInputView,
  KellyManualInput,
  LeverageResponse,
  Market,
  PlaybookConfirmRulesInput,
  PlaybookEmergencyExitResponse,
  PlaybookRuleSetResponse,
  PlaybookTodayResponse,
  PortfolioLimitsResponse,
  PortfolioSummaryResponse,
  Position,
  PositionsResponse,
  SectorListResponse,
  SettingsResponse,
  SignalsResponse,
  UpdatePositionInput,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const positionsTemplateCsvUrl = `${API_BASE}/api/positions/template.csv`;

/**
 * Error raised for any non-2xx response or network failure.
 * `fieldErrors` is populated when the backend returns a FastAPI-style
 * 422 validation error body (`{ detail: [{ loc, msg }] }`); callers can
 * use it to render field-level messages instead of a generic toast.
 *
 * `body` is the parsed JSON response, whatever shape it took (`null` when the
 * response carried no body at all, e.g. a network failure). It exists for
 * endpoints whose non-2xx `detail` is a **structured object rather than a
 * string or a validation-error array** — `KellyImportRefusal`
 * (`app/api/kelly.py`, 422 from `POST .../import-backtest`) is the first
 * caller: its `reason_code` / `frame` / `attempt_logged` / `selection_bias`
 * fields have no other way to reach a component through this class, since
 * neither `message` nor `fieldErrors` covers a `detail` that is a plain
 * object. Every existing call site keeps working unchanged — this field is
 * purely additive.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: Record<string, string>;
  readonly body: unknown;

  constructor(
    message: string,
    status: number,
    fieldErrors: Record<string, string> = {},
    body: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
    this.body = body;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

//: The closed set `KellyGateReasonCode` names (app/kelly/models.py, verified) —
//: used only to narrow `ApiError.body.detail.reason_code` before trusting it,
//: never rendered.
const KELLY_GATE_REASON_CODES: readonly KellyGateReasonCode[] = [
  "low_round_trips",
  "low_win_trips",
  "low_loss_trips",
  "pb_none",
  "symbol_mismatch",
  "insufficient_data",
];

/**
 * Reads a refused `POST .../import-backtest`'s `KellyImportRefusal` body back
 * out of an `ApiError` (`app/api/kelly.py`; 422 `detail` is the model's own
 * `model_dump()`, a plain object rather than FastAPI's usual validation-error
 * array — `ApiError.fieldErrors`/`message` do not reach it). Returns `null`
 * for any other shape, including a 4xx from a different endpoint, so a caller
 * can branch on the result rather than trust a status code alone.
 */
export function parseKellyImportRefusal(body: unknown): KellyImportRefusal | null {
  if (!isRecord(body) || !isRecord(body.detail)) return null;
  const detail = body.detail;
  const reasonCode = detail.reason_code;
  const message = detail.message;
  if (
    typeof reasonCode !== "string" ||
    !KELLY_GATE_REASON_CODES.includes(reasonCode as KellyGateReasonCode) ||
    typeof message !== "string" ||
    typeof detail.attempt_logged !== "string"
  ) {
    return null;
  }
  return {
    reason_code: reasonCode as KellyGateReasonCode,
    message,
    frame: typeof detail.frame === "string" ? detail.frame : null,
    attempt_logged: detail.attempt_logged,
    selection_bias: typeof detail.selection_bias === "string" ? detail.selection_bias : null,
    k_observed: typeof detail.k_observed === "number" ? detail.k_observed : 0,
    k_distinct_specs: typeof detail.k_distinct_specs === "number" ? detail.k_distinct_specs : 0,
  };
}

/**
 * Best-effort parse of FastAPI's default validation error envelope.
 * If the body does not match the expected shape we simply return an
 * empty map — callers fall back to the generic error message instead
 * of guessing field names.
 */
function parseValidationErrors(body: unknown): Record<string, string> {
  if (!isRecord(body) || !Array.isArray(body.detail)) {
    return {};
  }
  const result: Record<string, string> = {};
  for (const item of body.detail) {
    if (!isRecord(item)) continue;
    const loc = item.loc;
    const msg = item.msg;
    if (!Array.isArray(loc) || typeof msg !== "string") continue;
    const field = loc[loc.length - 1];
    if (typeof field === "string" || typeof field === "number") {
      result[String(field)] = msg;
    }
  }
  return result;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("無法連線到後端服務", 0);
  }

  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      // no JSON body on this error response; keep body as null
    }
    const fieldErrors = parseValidationErrors(body);
    const message =
      isRecord(body) && typeof body.detail === "string"
        ? body.detail
        : `請求失敗（HTTP ${res.status}）`;
    throw new ApiError(message, res.status, fieldErrors, body);
  }

  // 204 No Content / empty body responses (e.g. DELETE) have nothing to
  // parse. This cast is scoped to the no-body case only.
  const text = await res.text();
  if (text.length === 0) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}

export function getPositions(): Promise<PositionsResponse> {
  return request<PositionsResponse>("/api/positions");
}

export function createPosition(input: CreatePositionInput): Promise<Position> {
  return request<Position>("/api/positions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function updatePosition(id: number, input: UpdatePositionInput): Promise<Position> {
  return request<Position>(`/api/positions/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function deletePosition(id: number): Promise<void> {
  return request<void>(`/api/positions/${id}`, {
    method: "DELETE",
  });
}

export function getPortfolioSummary(): Promise<PortfolioSummaryResponse> {
  return request<PortfolioSummaryResponse>("/api/portfolio/summary");
}

/** FR-8: the five risk caps judged over the whole book (app/api/portfolio.py). */
export function getPortfolioLimits(): Promise<PortfolioLimitsResponse> {
  return request<PortfolioLimitsResponse>("/api/portfolio/limits");
}

/** The TWSE industry categories a TW position may declare (FR-12). */
export function getSectors(): Promise<SectorListResponse> {
  return request<SectorListResponse>("/api/positions/sectors");
}

export function importPositionsCsv(file: File): Promise<ImportPositionsResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return request<ImportPositionsResponse>("/api/positions/import", {
    method: "POST",
    body: formData,
  });
}

/* --- M7: signals / advice / leverage / backtest / settings / alerts ----- */

export function getSignals(
  symbol: string,
  market: Market,
  lookbackDays?: number,
): Promise<SignalsResponse> {
  const query = new URLSearchParams({ market });
  if (lookbackDays !== undefined) query.set("lookback_days", String(lookbackDays));
  return request<SignalsResponse>(`/api/signals/${encodeURIComponent(symbol)}?${query}`);
}

/** Same default `lookback_days` (540) and loader as `/api/signals` (app/api/bars.py, verified). */
export function getBars(symbol: string, market: Market, lookbackDays?: number): Promise<BarsResponse> {
  const query = new URLSearchParams({ market });
  if (lookbackDays !== undefined) query.set("lookback_days", String(lookbackDays));
  return request<BarsResponse>(`/api/bars/${encodeURIComponent(symbol)}?${query}`);
}

export function getAdvice(symbol: string, market: Market): Promise<AdviceResponse> {
  const query = new URLSearchParams({ market });
  return request<AdviceResponse>(`/api/advice/${encodeURIComponent(symbol)}?${query}`);
}

export function getLeverageChapter(symbol: string, market: Market): Promise<LeverageResponse> {
  const query = new URLSearchParams({ market });
  return request<LeverageResponse>(`/api/leverage/${encodeURIComponent(symbol)}?${query}`);
}

export function runBacktest(input: BacktestRequest): Promise<BacktestResponse> {
  return request<BacktestResponse>("/api/backtest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getSettings(): Promise<SettingsResponse> {
  return request<SettingsResponse>("/api/settings");
}

export function updateSettings(input: AppSettingsPatch): Promise<SettingsResponse> {
  return request<SettingsResponse>("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getAlerts(enabledOnly = false): Promise<AlertRuleListResponse> {
  const query = enabledOnly ? "?enabled_only=true" : "";
  return request<AlertRuleListResponse>(`/api/alerts${query}`);
}

export function createAlert(input: AlertRuleInput): Promise<AlertRule> {
  return request<AlertRule>("/api/alerts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

/**
 * `PATCH /api/alerts/{rule_id}` (app/api/alerts.py, verified) — partial edit,
 * chosen over `PUT` for the edit form (see `EditAlertRuleModal` doc comment
 * for the reasoning).
 */
export function patchAlert(id: number, input: AlertRulePatch): Promise<AlertRule> {
  return request<AlertRule>(`/api/alerts/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function deleteAlert(id: number): Promise<void> {
  return request<void>(`/api/alerts/${id}`, { method: "DELETE" });
}

/** `unacknowledged`: `true` only-pending, `false` only-acked, `undefined` all. */
export function getAlertEvents(unacknowledged?: boolean): Promise<AlertEventListResponse> {
  const query = unacknowledged === undefined ? "" : `?unacknowledged=${unacknowledged}`;
  return request<AlertEventListResponse>(`/api/alerts/events${query}`);
}

export function ackAlertEvent(id: number): Promise<AlertEvent> {
  return request<AlertEvent>(`/api/alerts/events/${id}/ack`, { method: "POST" });
}

export function evaluateAlertsNow(): Promise<AlertEvaluationResponse> {
  return request<AlertEvaluationResponse>("/api/alerts/evaluate", { method: "POST" });
}

/* --- Security directory (app/api/directory.py, FR-3/4/6/7) -------------- */

/**
 * `GET /api/directory/search` (backend, verified) — 代號前綴 + 名稱子字串
 * candidates for the NavBar combobox (FR-4). `limit` is left to the
 * backend's own default (12, per the dispatch order) unless a caller
 * overrides it; this app never does today.
 */
export function searchDirectory(q: string, limit?: number): Promise<DirectorySearchResponse> {
  const query = new URLSearchParams({ q });
  if (limit !== undefined) query.set("limit", String(limit));
  return request<DirectorySearchResponse>(`/api/directory/search?${query}`);
}

/**
 * `GET /api/directory/resolve/{symbol}` (backend, verified). Unlike every
 * other request helper in this module, a 404 here is not an exceptional
 * failure — it is the honest "not in the directory" signal FR-2/FR-6's Q1(b)
 * fallback is built on (miss -> ask the user to pick a market; miss on the
 * company-name lookup -> show the symbol alone). Callers branch on `null`
 * rather than catching `ApiError`.
 */
export async function resolveDirectorySymbol(symbol: string): Promise<DirectoryItem | null> {
  try {
    return await request<DirectoryItem>(`/api/directory/resolve/${encodeURIComponent(symbol)}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

/* --- 排程台 / Playbook (app/api/playbook.py, verified) ------------------- */

/**
 * `GET /api/playbook/today` (verified). Settles yesterday's due T+1 lines
 * first (idempotently) before evaluating, so `settlement` on the response is
 * the run that preceded this evaluation, not a stale one.
 */
export function getPlaybookToday(): Promise<PlaybookTodayResponse> {
  return request<PlaybookTodayResponse>("/api/playbook/today");
}

/**
 * `GET /api/playbook/rule-set` (verified). The thresholds of the rule version
 * in force plus the authorship record — read-only: reading the rules is not
 * adopting them (風控 R2, backend doc comment).
 */
export function getPlaybookRuleSet(): Promise<PlaybookRuleSetResponse> {
  return request<PlaybookRuleSetResponse>("/api/playbook/rule-set");
}

/**
 * `POST /api/playbook/confirm-rules` (verified). Adopts the rule set already in
 * force as the user's own and records the opening capital; idempotent, and the
 * body carries no threshold (鐵律④ cannot be routed around by re-confirming).
 */
export function postPlaybookConfirmRules(
  input: PlaybookConfirmRulesInput,
): Promise<PlaybookRuleSetResponse> {
  return request<PlaybookRuleSetResponse>("/api/playbook/confirm-rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

/**
 * `POST /api/playbook/emergency-exit` (verified). Takes no body by design —
 * CEO 裁決六: naming a symbol would turn the escape hatch into a discretionary
 * trade. All-or-nothing, works in every mode.
 */
export function postPlaybookEmergencyExit(): Promise<PlaybookEmergencyExitResponse> {
  return request<PlaybookEmergencyExitResponse>("/api/playbook/emergency-exit", {
    method: "POST",
  });
}

/* --- Kelly input (ADR-0006 D-8, C5, app/api/kelly.py) -------------------- */

/** `GET /api/kelly-inputs` — every stored input, in key order (D-8). Not used by `KellyInputsSection` today; kept for parity with the backend's own list route. */
export function getKellyInputs(): Promise<KellyInputListView> {
  return request<KellyInputListView>("/api/kelly-inputs");
}

/**
 * `GET /api/kelly-inputs/{symbol}/disclosures` — one instrument's Kelly
 * screen, every sentence already chosen server-side (K4c-1, 落地條件 3).
 * Answers 200 with `kelly_input: null` where `GET /{symbol}` answers 404:
 * "nothing entered" is a state this screen has its own copy for.
 */
export function getKellyDisclosures(
  symbol: string,
  market: Market,
): Promise<KellyInputDisclosuresView> {
  const query = new URLSearchParams({ market });
  return request<KellyInputDisclosuresView>(
    `/api/kelly-inputs/${encodeURIComponent(symbol)}/disclosures?${query}`,
  );
}

/** `PUT /api/kelly-inputs/{symbol}` — store a hand-entered pair (creates `manual`, or moves the effective pair of an existing row to `backtest_overridden`). */
export function putKellyInput(
  symbol: string,
  market: Market,
  input: KellyManualInput,
): Promise<KellyInputView> {
  const query = new URLSearchParams({ market });
  return request<KellyInputView>(`/api/kelly-inputs/${encodeURIComponent(symbol)}?${query}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

/** `DELETE /api/kelly-inputs/{symbol}` — removes the input row only; the import-attempt log (K_observed) is untouched (約束 35). */
export function deleteKellyInput(symbol: string, market: Market): Promise<void> {
  const query = new URLSearchParams({ market });
  return request<void>(`/api/kelly-inputs/${encodeURIComponent(symbol)}?${query}`, {
    method: "DELETE",
  });
}

/**
 * `POST /api/kelly-inputs/{symbol}/import-backtest` — re-runs a backtest
 * server-side and stores the p/b **this server** computed (D-3). The body is
 * a request, never a result: there is no `backtest_id` to quote, so every
 * call re-executes the run. **條件 74 (最重要的落地條件)**: this is the
 * *only* place in the whole frontend allowed to call this endpoint — every
 * caller must go through `KellyImportDialog`'s confirm handler, never a
 * direct button press. `tests/callSiteGuard.test.ts` (this app) asserts the
 * call-site count.
 */
export function importKellyBacktest(
  symbol: string,
  market: Market,
  body: BacktestRequest,
): Promise<KellyInputView> {
  const query = new URLSearchParams({ market });
  return request<KellyInputView>(
    `/api/kelly-inputs/${encodeURIComponent(symbol)}/import-backtest?${query}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}
