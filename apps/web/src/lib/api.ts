/**
 * API client. The access token lives only in memory; the refresh token is an httpOnly cookie scoped to
 * /api/v1/auth (set by FastAPI, proxied same-origin by Next.js). On 401 we refresh once and retry.
 */

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: unknown, public requestId?: string) {
    super(message);
  }
}

let accessToken: string | null = null;
let refreshing: Promise<string | null> | null = null;
const listeners = new Set<(t: string | null) => void>();

export function setAccessToken(t: string | null) {
  accessToken = t;
  listeners.forEach((l) => l(t));
}
export function getAccessToken() {
  return accessToken;
}
export function onTokenChange(fn: (t: string | null) => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshing) {
    refreshing = fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" })
      .then(async (r) => (r.ok ? ((await r.json()).access_token as string) : null))
      .catch(() => null)
      .then((t) => {
        setAccessToken(t);
        return t;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

type Options = Omit<RequestInit, "body"> & { body?: unknown; idempotencyKey?: string; raw?: boolean };

async function parseError(r: Response): Promise<ApiError> {
  try {
    const j = await r.json();
    const e = j.error ?? {};
    return new ApiError(r.status, e.code ?? "http_error", e.message ?? r.statusText, e.details, e.request_id);
  } catch {
    return new ApiError(r.status, "http_error", r.statusText || "Request failed");
  }
}

export async function api<T = any>(path: string, opts: Options = {}, retry = true): Promise<T> {
  const headers = new Headers(opts.headers);
  const isForm = typeof FormData !== "undefined" && opts.body instanceof FormData;
  if (opts.body !== undefined && !isForm) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (opts.idempotencyKey) headers.set("Idempotency-Key", opts.idempotencyKey);
  const r = await fetch(`/api/v1${path}`, {
    ...opts,
    headers,
    credentials: "include",
    body: opts.body === undefined ? undefined : isForm ? (opts.body as FormData) : JSON.stringify(opts.body),
  });
  if (r.status === 401 && retry && !path.startsWith("/auth/")) {
    const t = await refreshAccessToken();
    if (t) return api<T>(path, opts, false);
  }
  if (!r.ok) throw await parseError(r);
  if (opts.raw) return r as unknown as T;
  if (r.status === 204) return undefined as T;
  const ct = r.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? r.json() : r.text()) as Promise<T>;
}

export async function downloadFile(path: string, filename: string) {
  const r = await api<Response>(path, { raw: true });
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Server-Sent Events over fetch so the Authorization header can be sent (EventSource cannot set headers). */
export function streamEvents(path: string, onEvent: (event: string, data: any) => void, onEnd?: () => void): () => void {
  const ctrl = new AbortController();
  (async () => {
    try {
      const headers: Record<string, string> = {};
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
      const r = await fetch(`/api/v1${path}`, { headers, signal: ctrl.signal, credentials: "include" });
      if (!r.ok || !r.body) throw await parseError(r);
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const block = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          let event = "message";
          let data = "";
          for (const line of block.split("\n")) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:")) data += line.slice(5).trim();
          }
          if (data) {
            try {
              onEvent(event, JSON.parse(data));
            } catch {
              onEvent(event, data);
            }
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") console.warn("stream error", e);
    } finally {
      onEnd?.();
    }
  })();
  return () => ctrl.abort();
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === "validation_error" && Array.isArray(e.details)) {
      return (e.details as { loc: string[]; msg: string }[]).map((d) => `${d.loc.slice(1).join(".")}: ${d.msg}`).join("; ");
    }
    if (e.details && typeof e.details === "object" && !Array.isArray(e.details)) {
      const extra = Object.entries(e.details as Record<string, unknown>).slice(0, 4)
        .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join("; ");
      return extra ? `${e.message} (${extra})` : e.message;
    }
    return e.message;
  }
  return e instanceof Error ? e.message : "Something went wrong";
}

export const newIdempotencyKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
