import { afterEach, describe, expect, it, vi } from "vitest";

import { requestJson } from "../src/apiClient";

describe("apiClient", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("returns parsed JSON for successful responses", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(requestJson<{ ok: boolean }>("/api/health")).resolves.toEqual({ ok: true });
  });

  it("rejects when a request times out", async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => {
      const signal = init?.signal;
      return new Promise((_resolve, reject) => {
        signal?.addEventListener("abort", () => {
          reject(new DOMException("Request aborted", "AbortError"));
        });
      });
    });

    const promise = requestJson("/api/slow", { timeoutMs: 10 });
    const rejection = expect(promise).rejects.toThrow("Request timed out after 10 ms");
    await vi.advanceTimersByTimeAsync(10);

    await rejection;
  });

  it("preserves caller aborts instead of reporting them as timeouts", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => {
      const signal = init?.signal;
      return new Promise((_resolve, reject) => {
        signal?.addEventListener("abort", () => {
          reject(new DOMException("Request aborted", "AbortError"));
        });
      });
    });

    const promise = requestJson("/api/slow", {
      signal: controller.signal,
      timeoutMs: 1_000,
    });
    controller.abort();

    await expect(promise).rejects.toMatchObject({ name: "AbortError" });
  });
});
