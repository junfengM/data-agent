import { parseApiError } from "./apiErrors";

const DEFAULT_TIMEOUT_MS = 300_000;

type RequestOptions = RequestInit & {
  timeoutMs?: number;
};

declare global {
  interface Window {
    __DATA_AGENT_DESKTOP__?: {
      apiBaseUrl?: string;
    };
  }
}

export function resolveApiUrl(input: string | URL): string {
  const raw = input.toString();
  if (/^[a-z][a-z\d+\-.]*:/i.test(raw)) return raw;

  const apiBaseUrl = window.__DATA_AGENT_DESKTOP__?.apiBaseUrl;
  if (!apiBaseUrl || !raw.startsWith("/api/")) return raw;

  return new URL(raw, normalizeBaseUrl(apiBaseUrl)).toString();
}

export function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return fetch(resolveFetchInput(input), init);
}

export async function requestJson<T>(
  input: RequestInfo | URL,
  init?: RequestOptions,
): Promise<T> {
  const response = await fetchWithTimeout(input, init);
  if (!response.ok) throw new Error(await parseApiError(response));
  return response.json() as Promise<T>;
}

export async function requestVoid(
  input: RequestInfo | URL,
  init?: RequestOptions,
): Promise<void> {
  const response = await fetchWithTimeout(input, init);
  if (!response.ok) throw new Error(await parseApiError(response));
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestOptions = {},
): Promise<Response> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, ...fetchInit } = init;
  if (signal?.aborted) {
    throw new DOMException("Request aborted", "AbortError");
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const abortHandler = () => controller.abort();
  signal?.addEventListener("abort", abortHandler, { once: true });

  try {
    return await fetch(resolveFetchInput(input), {
      ...fetchInit,
      signal: controller.signal,
    });
  } catch (error) {
    if (controller.signal.aborted && !signal?.aborted) {
      throw new Error(`Request timed out after ${timeoutMs} ms`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
    signal?.removeEventListener("abort", abortHandler);
  }
}

function resolveFetchInput(input: RequestInfo | URL): RequestInfo | URL {
  if (typeof input === "string" || input instanceof URL) return resolveApiUrl(input);
  return new Request(resolveApiUrl(input.url), input);
}

function normalizeBaseUrl(value: string): string {
  return value.endsWith("/") ? value : `${value}/`;
}
