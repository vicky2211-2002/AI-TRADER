import { app, BrowserWindow, ipcMain, shell, dialog } from "electron";
import { spawn, ChildProcess } from "node:child_process";
import { existsSync, mkdirSync, createWriteStream } from "node:fs";
import path from "node:path";
import net from "node:net";
import os from "node:os";

const isDev = !!process.env.VITE_DEV_SERVER_URL;
const CORE_PORT = Number(process.env.AI_TRADER_PORT || 8765);
const CORE_URL = `http://127.0.0.1:${CORE_PORT}`;

let mainWindow: BrowserWindow | null = null;
let coreProcess: ChildProcess | null = null;
let coreSpawnedByUs = false;

function coreDir(): string {
  if (app.isPackaged) return path.join(process.resourcesPath, "core");
  return path.resolve(__dirname, "..", "..", "core");
}

function skillsDir(): string {
  if (app.isPackaged) return path.join(process.resourcesPath, "skills");
  return path.resolve(__dirname, "..", "..", "skills");
}

/**
 * Bundled Python core (PyInstaller sidecar) shipped inside the installer.
 * When present, the app never needs a system Python installation.
 */
function bundledCore(): string | null {
  if (!app.isPackaged) return null;
  const exe = process.platform === "win32" ? "aitrader-core.exe" : "aitrader-core";
  const full = path.join(process.resourcesPath, "core-runtime", exe);
  return existsSync(full) ? full : null;
}

/**
 * Bundled Node.js (includes npx) for MCP servers.
 * Shipped as resources/node/node.exe + resources/node/npx.cmd on Windows.
 */
function bundledNodeDir(): string | null {
  if (!app.isPackaged) return null;
  const dir = path.join(process.resourcesPath, "node");
  return existsSync(dir) ? dir : null;
}

/**
 * Bundled uv binary for MCP servers.
 * Shipped as resources/uv/uv.exe on Windows, resources/uv/uv on macOS/Linux.
 */
function bundledUvPath(): string | null {
  if (!app.isPackaged) return null;
  const exe = process.platform === "win32" ? "uv.exe" : "uv";
  const full = path.join(process.resourcesPath, "uv", exe);
  return existsSync(full) ? full : null;
}

function pythonCandidates(): { cmd: string; args: string[] }[] {
  if (process.env.AI_TRADER_PYTHON) {
    return [{ cmd: process.env.AI_TRADER_PYTHON, args: [] }];
  }
  if (process.platform === "win32") {
    return [
      { cmd: "py", args: ["-3.12"] },
      { cmd: "py", args: ["-3"] },
      { cmd: "python", args: [] },
    ];
  }
  return [
    { cmd: "python3", args: [] },
    { cmd: "python", args: [] },
  ];
}

function getLanIp(): string | null {
  const interfaces = os.networkInterfaces();
  for (const name of Object.keys(interfaces)) {
    for (const iface of interfaces[name] || []) {
      if (iface.family === "IPv4" && !iface.internal) {
        return iface.address;
      }
    }
  }
  return null;
}

function portOpen(port: number, timeout = 700): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let done = false;
    const finish = (value: boolean) => {
      if (done) return;
      done = true;
      socket.destroy();
      resolve(value);
    };
    socket.setTimeout(timeout);
    socket.once("connect", () => finish(true));
    socket.once("timeout", () => finish(false));
    socket.once("error", () => finish(false));
    socket.connect(port, "127.0.0.1");
  });
}

async function coreHealthy(): Promise<boolean> {
  try {
    const res = await fetch(`${CORE_URL}/api/health`, { signal: AbortSignal.timeout(1500) });
    if (!res.ok) return false;
    const body = (await res.json()) as { app?: string };
    return body.app === "AI-TRADER";
  } catch {
    return false;
  }
}

async function waitForCore(attempts = 60): Promise<boolean> {
  for (let i = 0; i < attempts; i += 1) {
    if (await coreHealthy()) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function startCore(): void {
  if (coreProcess) return;
  const logs = path.join(app.getPath("userData"), "logs");
  mkdirSync(logs, { recursive: true });
  const log = createWriteStream(path.join(logs, "core.log"), { flags: "a" });
  const dir = coreDir();
  const entry = path.join(dir, "main.py");
  const bundled = bundledCore();

  if (!bundled && !existsSync(entry)) {
    dialog.showErrorBox("AI-TRADER", `Core not found at ${entry}`);
    return;
  }

  const lanIp = getLanIp();
  // Build PATH with bundled Node.js (npx) and uv so MCP servers work out of the box
  const extraPaths: string[] = [];
  const nodeDir = bundledNodeDir();
  if (nodeDir) extraPaths.push(nodeDir);
  const uvPath = bundledUvPath();
  if (uvPath) extraPaths.push(path.dirname(uvPath));
  const pathEnv = extraPaths.length > 0 ? extraPaths.join(path.delimiter) + path.delimiter + (process.env.PATH || "") : (process.env.PATH || "");

  const env: Record<string, string | undefined> = {
    ...process.env,
    PATH: pathEnv,
    AI_TRADER_HOME: process.env.AI_TRADER_HOME || path.join(app.getPath("userData")),
    AI_TRADER_SKILLS: process.env.AI_TRADER_SKILLS || skillsDir(),
    AI_TRADER_PORT: String(CORE_PORT),
    AI_TRADER_HOST: "0.0.0.0",
    PYTHONUNBUFFERED: "1",
    PYTHONIOENCODING: "utf-8",
  };
  if (app.isPackaged) {
    env.AI_TRADER_UI = path.join(process.resourcesPath, "ui");
  }

  const launch = (cmd: string, args: string[], cwd: string) => {
    const child = spawn(cmd, args, {
      cwd,
      env,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    child.stdout?.pipe(log);
    child.stderr?.pipe(log);
    child.on("error", () => {
      /* try next candidate */
    });
    child.on("exit", (code) => {
      log.write(`\n[core exited ${code}]\n`);
      coreProcess = null;
    });
    coreProcess = child;
    coreSpawnedByUs = true;
    log.write(`\n[start] ${cmd} ${args.join(" ")}\n`);
    if (lanIp) {
      log.write(`[lan] ${lanIp}:${CORE_PORT}\n`);
    }
  };

  if (bundled) {
    launch(bundled, [], path.dirname(bundled));
    return;
  }

  for (const candidate of pythonCandidates()) {
    try {
      launch(candidate.cmd, [...candidate.args, entry], dir);
      break;
    } catch {
      continue;
    }
  }
}

function stopCore(): void {
  if (!coreProcess || !coreSpawnedByUs) return;
  try {
    if (process.platform === "win32" && coreProcess.pid) {
      spawn("taskkill", ["/pid", String(coreProcess.pid), "/T", "/F"], { windowsHide: true });
    } else {
      coreProcess.kill("SIGTERM");
    }
  } catch {
    /* ignore */
  }
  coreProcess = null;
}

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#faf9f5",
    title: "AI-TRADER",
    show: false,
    autoHideMenuBar: true,
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: true,
    },
  });

  mainWindow.once("ready-to-show", () => mainWindow?.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });

  if (isDev) {
    await mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL as string);
    mainWindow.webContents.openDevTools({ mode: "detach" });
  } else {
    await mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

ipcMain.handle("core:url", () => CORE_URL);

ipcMain.handle("core:lan-info", () => ({
  lanIp: getLanIp(),
  port: CORE_PORT,
  coreUrl: CORE_URL,
  mobileUrl: getLanIp() ? `http://${getLanIp()}:${CORE_PORT}` : null,
}));

ipcMain.handle("core:mt5-info", async () => {
  try {
    const res = await fetch(`${CORE_URL}/api/brokers/mt5/status`, { signal: AbortSignal.timeout(2000) });
    if (res.ok) return await res.json();
  } catch {
    // Fallback to local check
  }
  return { mt5Found: false, message: "Core not ready" };
});

ipcMain.handle("core:restart", async () => {
  stopCore();
  await startCore();
  return waitForCore();
});

ipcMain.handle("app:info", () => ({
  version: app.getVersion(),
  platform: process.platform,
  coreUrl: CORE_URL,
  packaged: app.isPackaged,
}));

app.whenReady().then(async () => {
  const already = await coreHealthy();
  if (!already) startCore();
  await waitForCore(already ? 2 : 60);
  await createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", stopCore);