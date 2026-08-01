import { describe, expect, it } from "vitest";
import { resolveApiUrl } from "./apiClient";

declare global {
  interface Window {
    __DATA_AGENT_DESKTOP__?: {
      apiBaseUrl?: string;
    };
  }
}

describe("resolveApiUrl", () => {
  it("keeps relative API paths relative in browser mode", () => {
    delete window.__DATA_AGENT_DESKTOP__;

    expect(resolveApiUrl("/api/health")).toBe("/api/health");
  });

  it("resolves relative API paths against the desktop backend URL", () => {
    window.__DATA_AGENT_DESKTOP__ = { apiBaseUrl: "http://127.0.0.1:43123" };

    expect(resolveApiUrl("/api/health")).toBe("http://127.0.0.1:43123/api/health");
  });

  it("preserves absolute URLs", () => {
    window.__DATA_AGENT_DESKTOP__ = { apiBaseUrl: "http://127.0.0.1:43123" };

    expect(resolveApiUrl("https://example.com/api/health")).toBe("https://example.com/api/health");
  });
});
