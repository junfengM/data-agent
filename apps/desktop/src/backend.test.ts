import { describe, expect, it } from "bun:test";
import type { ChildProcess } from "node:child_process";
import path from "node:path";
import {
  buildApiBaseUrl,
  buildBackendEnv,
  resolvePythonExecutable,
  resolveRepoRoot,
  waitForBackendOrTerminate,
} from "./backend";

describe("desktop backend helpers", () => {
  it("resolves the repository root from the desktop app directory", () => {
    const appPath = path.join("/repo", "apps", "desktop");

    expect(resolveRepoRoot({ appPath })).toBe("/repo");
  });

  it("prefers an explicit repository root override", () => {
    expect(resolveRepoRoot({ appPath: "/ignored", repoRootOverride: "/custom/data_agent" })).toBe(
      "/custom/data_agent",
    );
  });

  it("resolves the repository root from a packaged app inside the repo release directory", () => {
    const appPath = path.join(
      "/repo",
      "apps",
      "desktop",
      "release",
      "mac-arm64",
      "Data Agent.app",
      "Contents",
      "Resources",
      "app.asar",
    );

    expect(resolveRepoRoot({ appPath })).toBe("/repo");
  });

  it("resolves the repo-local virtualenv Python executable", () => {
    expect(resolvePythonExecutable("/repo")).toBe("/repo/server/.venv/bin/python");
  });

  it("builds a loopback API base URL", () => {
    expect(buildApiBaseUrl(43123)).toBe("http://127.0.0.1:43123");
  });

  it("builds backend environment without exposing the desktop shell path as HOME", () => {
    const env = buildBackendEnv({
      baseEnv: { HOME: "/Users/example", PATH: "/usr/bin" },
      repoRoot: "/repo",
      port: 43123,
    });

    expect(env.DATA_AGENT_DESKTOP).toBe("1");
    expect(env.DATA_AGENT_PORT).toBe("43123");
    expect(env.PYTHONPATH).toBeUndefined();
    expect(env.HOME).toBe("/Users/example");
    expect(env.PATH).toBe("/usr/bin");
  });

  it("terminates the backend process when its health check fails", async () => {
    let signal: NodeJS.Signals | number | undefined;
    const child = {
      kill(nextSignal?: NodeJS.Signals | number) {
        signal = nextSignal;
        return true;
      },
    } as ChildProcess;
    const healthError = new Error("health check failed");

    await expect(
      waitForBackendOrTerminate("http://127.0.0.1:43123", child, async () => {
        throw healthError;
      }),
    ).rejects.toBe(healthError);
    expect(signal).toBe("SIGTERM");
  });
});
