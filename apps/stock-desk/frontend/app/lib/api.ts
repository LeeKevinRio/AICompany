import type {
  CreatePositionInput,
  HealthResponse,
  ImportPositionsResponse,
  PortfolioSummaryResponse,
  Position,
  PositionsResponse,
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

export function importPositionsCsv(file: File): Promise<ImportPositionsResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return request<ImportPositionsResponse>("/api/positions/import", {
    method: "POST",
    body: formData,
  });
}
