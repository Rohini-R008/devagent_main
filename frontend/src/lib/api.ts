import type {
  Review,
  DebugResult,
  DebugScan,
  HealthStatus,
} from "./types";

// Base URL of the FastAPI backend. Override with NEXT_PUBLIC_API_URL in
// .env.local; defaults to the local uvicorn dev server.
const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    // Network-level failure (backend down, CORS, DNS, etc.)
    throw new ApiError(
      `Can't reach the backend at ${API_URL}. Is it running?`,
      0
    );
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* response wasn't JSON; keep statusText */
    }
    throw new ApiError(detail, res.status);
  }

  return res.json() as Promise<T>;
}

export const api = {
  baseUrl: API_URL,

  health: () => request<HealthStatus>("/health"),

  listReviews: (limit = 50) => request<Review[]>(`/reviews?limit=${limit}`),

  scanRepo: (repoPath: string) =>
    request<DebugResult>("/debug/scan", {
      method: "POST",
      body: JSON.stringify({ repo_path: repoPath }),
    }),

  analyzeTraceback: (repoPath: string, tracebackText: string) =>
    request<DebugResult>("/debug/analyze", {
      method: "POST",
      body: JSON.stringify({
        repo_path: repoPath,
        traceback_text: tracebackText,
      }),
    }),

  indexRepo: (repoPath: string) =>
    request<unknown>("/debug/index", {
      method: "POST",
      body: JSON.stringify({ repo_path: repoPath }),
    }),

  debugHistory: (limit = 50) =>
    request<DebugScan[]>(`/debug/history?limit=${limit}`),
};

export { ApiError };