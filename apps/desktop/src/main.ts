import { app, BrowserWindow, Menu, shell } from "electron";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  type BackendProcess,
  resolveRepoRoot,
  startBackend,
  stopBackend,
} from "./backend.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow: BrowserWindow | null = null;
let backend: BackendProcess | null = null;

async function createWindow(): Promise<void> {
  const repoRoot = resolveRepoRoot({
    appPath: app.getAppPath(),
    repoRootOverride: process.env.DATA_AGENT_REPO_ROOT,
  });
  const runtimeConfigPath = path.join(app.getPath("userData"), "runtime-config.json");

  mainWindow = new BrowserWindow({
    backgroundColor: "#f6f7f4",
    height: 920,
    minHeight: 720,
    minWidth: 1080,
    show: false,
    title: "Data Agent",
    webPreferences: {
      additionalArguments: [`--data-agent-config=${runtimeConfigPath}`],
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.cjs"),
      sandbox: false,
    },
    width: 1440,
  });

  mainWindow.once("ready-to-show", () => mainWindow?.show());
  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  await mainWindow.loadURL(startupPage());

  try {
    backend = await startBackend({
      appPath: app.getAppPath(),
      repoRootOverride: process.env.DATA_AGENT_REPO_ROOT,
    });
    fs.writeFileSync(
      runtimeConfigPath,
      JSON.stringify({ apiBaseUrl: backend.apiBaseUrl }, null, 2),
      "utf8",
    );
    mainWindow.webContents.session.setPermissionRequestHandler((_webContents, _permission, callback) => {
      callback(false);
    });
    mainWindow.webContents.on("will-navigate", (event, targetUrl) => {
      if (targetUrl.startsWith("http://127.0.0.1:")) return;
      if (targetUrl.startsWith("file://")) return;
      event.preventDefault();
      shell.openExternal(targetUrl);
    });
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
      shell.openExternal(url);
      return { action: "deny" };
    });
    mainWindow.webContents.session.clearCache();
    mainWindow.webContents.session.setPermissionCheckHandler(() => false);
    await mainWindow.loadFile(resolveWebIndexPath(repoRoot));
  } catch (error) {
    await mainWindow.loadURL(errorPage(error, repoRoot));
  }
}

function resolveWebIndexPath(repoRoot: string): string {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "web-dist", "index.html");
  }
  return path.join(repoRoot, "apps", "web", "dist", "index.html");
}

function startupPage(): string {
  return htmlDataUrl(`
    <main>
      <h1>Data Agent</h1>
      <p>正在启动本地分析引擎...</p>
    </main>
  `);
}

function errorPage(error: unknown, repoRoot: string): string {
  const message = error instanceof Error ? error.message : String(error);
  return htmlDataUrl(`
    <main>
      <h1>启动失败</h1>
      <p>Data Agent 无法启动本地后端。</p>
      <dl>
        <dt>Repository</dt>
        <dd>${escapeHtml(repoRoot)}</dd>
        <dt>Error</dt>
        <dd>${escapeHtml(message)}</dd>
      </dl>
      <p class="hint">请确认已创建 <code>server/.venv</code> 并安装后端依赖。也可以设置 <code>DATA_AGENT_REPO_ROOT</code> 指向仓库目录。</p>
    </main>
  `);
}

function htmlDataUrl(body: string): string {
  const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Data Agent</title>
  <style>
    :root { color: #18211f; background: #f6f7f4; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; }
    main { width: min(560px, calc(100vw - 48px)); }
    h1 { margin: 0 0 12px; font-size: 28px; font-weight: 700; letter-spacing: 0; }
    p { color: #4c5954; font-size: 14px; line-height: 1.6; }
    dl { border: 1px solid #d8ded8; background: #fff; padding: 16px; }
    dt { color: #66736d; font-size: 12px; margin-top: 12px; }
    dt:first-child { margin-top: 0; }
    dd { margin: 4px 0 0; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; word-break: break-word; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .hint { color: #6d4c2f; }
  </style>
</head>
<body>${body}</body>
</html>`;
  return `data:text/html;charset=utf-8,${encodeURIComponent(html)}`;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function installMenu(): void {
  const repoRoot = resolveRepoRoot({
    appPath: app.getAppPath(),
    repoRootOverride: process.env.DATA_AGENT_REPO_ROOT,
  });
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    {
      label: "Data Agent",
      submenu: [
        { role: "about" },
        { type: "separator" },
        { label: "打开工作区目录", click: () => shell.openPath(path.join(repoRoot, "workspace")) },
        { label: "打开仓库目录", click: () => shell.openPath(repoRoot) },
        { type: "separator" },
        { role: "quit" },
      ],
    },
    { role: "editMenu" },
    { role: "viewMenu" },
  ]));
}

app.whenReady().then(async () => {
  installMenu();
  await createWindow();
});

app.on("window-all-closed", () => {
  app.quit();
});

app.on("before-quit", () => {
  stopBackend(backend);
});
