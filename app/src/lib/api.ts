import type { ChatEvent } from "./types";

const DEFAULT_URL = "http://127.0.0.1:8765";

type NativeBridge = {
  aiTrader?: { coreUrl?: string | (() => string | Promise<string>) };
};

export function getCoreUrl(): string {
  const stored = localStorage.getItem("aitrader.coreUrl");
  if (stored) return stored.replace(/\/$/, "");
  const bridge = (window as unknown as NativeBridge).aiTrader;
  const value = bridge?.coreUrl;
  if (typeof value === "string" && value) return value.replace(/\/$/, "");
  return DEFAULT_URL;
}

/** Resolve the real core URL, asking the desktop bridge when it exposes one. */
export async function resolveCoreUrl(): Promise<string> {
  const stored = localStorage.getItem("aitrader.coreUrl");
  if (stored) return stored.replace(/\/$/, "");
  const bridge = (window as unknown as NativeBridge).aiTrader;
  const value = bridge?.coreUrl;
  if (typeof value === "function") {
    try {
      const resolved = await value();
      if (resolved) return resolved.replace(/\/$/, "");
    } catch {
      /* fall through to default */
    }
  }
  return getCoreUrl();
}

export function setCoreUrl(url: string): void {
  localStorage.setItem("aitrader.coreUrl", url.replace(/\/$/, ""));
}

export function getToken(): string {
  return localStorage.getItem("aitrader.token") || "";
}

export function setToken(token: string): void {
  if (token) localStorage.setItem("aitrader.token", token);
  else localStorage.removeItem("aitrader.token");
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) h["X-AI-Trader-Token"] = token;
  return h;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${getCoreUrl()}${path}`, {
    method,
    headers: headers(),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : text || res.statusText;
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

export async function streamChat(
  body: Record<string, unknown>,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${getCoreUrl()}/api/chat/stream`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trim())
        .join("");
      if (!line) continue;
      try {
        onEvent(JSON.parse(line) as ChatEvent);
      } catch {
        /* ignore keep-alive */
      }
    }
  }
}

export function timeAgo(ts: number): string {
  if (!ts) return "";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function fmtMoney(value: unknown, currency = "USD"): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value ?? "-");
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 2 }).format(n);
  } catch {
    return n.toFixed(2);
  }
}
