import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";

type EnvRecord = Record<string, string | undefined>;

export type ResolveRepoRootOptions = {
  appPath: string;
  repoRootOverride?: string;
};

export type BackendEnvOptions = {
  baseEnv?: EnvRecord;
  repoRoot: string;
  port: number;
};

export type BackendProcess = {
  apiBaseUrl: string;
  logPath: string;
  process: ChildProcess;
};

export function resolveRepoRoot(options: ResolveRepoRootOptions): string {
  if (options.repoRootOverride?.trim()) return path.resolve(options.repoRootOverride);

  const appPath = path.resolve(options.appPath);
  for (const candidate of ancestorPaths(appPath)) {
    if (looksLikeRepoRoot(candidate)) return candidate;
  }

  const syntheticRepoRoot = inferRepoRootFromPathShape(appPath);
  if (syntheticRepoRoot) return syntheticRepoRoot;

  return path.resolve(appPath, "..", "..");
}

function inferRepoRootFromPathShape(appPath: string): string | null {
  const parts = appPath.split(path.sep);
  const appsIndex = parts.lastIndexOf("apps");
  if (appsIndex >= 0 && parts[appsIndex + 1] === "desktop") {
    return parts.slice(0, appsIndex).join(path.sep) || path.sep;
  }
  if (path.basename(appPath) === "desktop" && path.basename(path.dirname(appPath)) === "apps") {
    return path.resolve(appPath, "..", "..");
  }
  if (path.basename(appPath) === "dist") {
    return path.resolve(appPath, "..", "..", "..");
  }
  return null;
}

function ancestorPaths(start: string): string[] {
  const paths: string[] = [];
  let current = start;
  while (true) {
    paths.push(current);
    const parent = path.dirname(current);
    if (parent === current) return paths;
    current = parent;
  }
}

export function resolvePythonExecutable(repoRoot: string): string {
  return path.join(repoRoot, "server", ".venv", "bin", "python");
}

export function buildApiBaseUrl(port: number): string {
  return `http://127.0.0.1:${port}`;
}

export function buildBackendEnv(options: BackendEnvOptions): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const [key, value] of Object.entries(options.baseEnv ?? process.env)) {
    if (value != null) env[key] = value;
  }
  delete env.PYTHONPATH;
  env.DATA_AGENT_DESKTOP = "1";
  env.DATA_AGENT_PORT = String(options.port);
  env.DATA_AGENT_REPO_ROOT = options.repoRoot;
  return env;
}

export async function findAvailablePort(host = "127.0.0.1"): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, host, () => {
      const address = server.address();
      server.close(() => {
        if (!address || typeof address === "string") {
          reject(new Error("Unable to allocate a backend port"));
          return;
        }
        resolve(address.port);
      });
    });
  });
}

export async function startBackend(options: {
  appPath: string;
  repoRootOverride?: string;
  baseEnv?: EnvRecord;
}): Promise<BackendProcess> {
  const repoRoot = resolveRepoRoot({
    appPath: options.appPath,
    repoRootOverride: options.repoRootOverride ?? process.env.DATA_AGENT_REPO_ROOT,
  });
  const pythonExecutable = resolvePythonExecutable(repoRoot);
  if (!fs.existsSync(pythonExecutable)) {
    throw new Error(`Python virtualenv not found: ${pythonExecutable}`);
  }

  const port = await findAvailablePort();
  const apiBaseUrl = buildApiBaseUrl(port);
  const logPath = createBackendLogPath(repoRoot);
  const logStream = fs.createWriteStream(logPath, { flags: "a" });
  const child = spawn(
    pythonExecutable,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port)],
    {
      cwd: path.join(repoRoot, "server"),
      env: buildBackendEnv({ baseEnv: options.baseEnv, repoRoot, port }),
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  child.stdout.pipe(logStream, { end: false });
  child.stderr.pipe(logStream, { end: false });
  child.once("close", () => logStream.end());

  await waitForBackendOrTerminate(apiBaseUrl, child);
  return { apiBaseUrl, logPath, process: child };
}

export async function waitForBackendOrTerminate(
  apiBaseUrl: string,
  child: ChildProcess,
  healthCheck: (apiBaseUrl: string) => Promise<void> = waitForBackendHealth,
): Promise<void> {
  try {
    await healthCheck(apiBaseUrl);
  } catch (error) {
    child.kill("SIGTERM");
    throw error;
  }
}

export async function waitForBackendHealth(
  apiBaseUrl: string,
  options: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<void> {
  const timeoutMs = options.timeoutMs ?? 30_000;
  const intervalMs = options.intervalMs ?? 250;
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown = null;

  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${apiBaseUrl}/api/health`);
      if (response.ok) return;
      lastError = new Error(`Health check returned ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await delay(intervalMs);
  }

  throw new Error(`Backend did not become healthy within ${timeoutMs} ms: ${String(lastError)}`);
}

export function stopBackend(backend: BackendProcess | null): void {
  if (!backend || backend.process.killed) return;
  backend.process.kill("SIGTERM");
}

function looksLikeRepoRoot(candidate: string): boolean {
  return fs.existsSync(path.join(candidate, "server", "app", "main.py"))
    && fs.existsSync(path.join(candidate, "apps", "web", "package.json"));
}

function createBackendLogPath(repoRoot: string): string {
  const logDir = path.join(repoRoot, "workspace", "desktop-logs");
  fs.mkdirSync(logDir, { recursive: true });
  return path.join(logDir, `backend-${new Date().toISOString().replace(/[:.]/g, "-")}.log`);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
