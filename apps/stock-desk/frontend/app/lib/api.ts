import type {
  AdviceResponse,
  AlertEvaluationResponse,
  AlertEvent,
  AlertEventListResponse,
  AlertRule,
  AlertRuleInput,
  AlertRuleListResponse,
  AppSettingsPatch,
  BacktestRequest,
  BacktestResponse,
  BarsResponse,
  CreatePositionInput,
  HealthResponse,
  ImportPositionsResponse,
  LeverageResponse,
  Market,
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
 */
export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: Record<string, string>;

  constructor(message: string, status: number, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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
    throw new ApiError(message, res.status, fieldErrors);
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
