import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, Menu, RefreshCw, Sparkles, WifiOff } from "lucide-react";
import type { Bootstrap, McpCatalogItem, Settings } from "./lib/types";
import { api, getCoreUrl, setCoreUrl } from "./lib/api";
import { Sidebar, type View } from "./components/Sidebar";
import { DashboardView } from "./components/DashboardView";
import { ChatView } from "./components/ChatView";
import { ModelsView } from "./components/ModelsView";
import { McpView } from "./components/McpView";
import { SkillsView } from "./components/SkillsView";
import { BrokersView } from "./components/BrokersView";
import { TradesView } from "./components/TradesView";
import { SettingsView } from "./components/SettingsView";
import { Spinner } from "./components/ui";

const THEME_KEY = "aitrader.theme";

const VIEW_TITLES: Record<View, string> = {
  dashboard: "Autopilot",
  chat: "Chat",
  models: "Models",
  mcp: "MCP servers",
  skills: "Skills",
  brokers: "Brokers",
  trades: "Trades & risk",
  settings: "Settings",
};

function readTheme(): string {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "dark" || stored === "light") return stored;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function App() {
  const [boot, setBoot] = useState<Bootstrap | null>(null);
  const [catalog, setCatalog] = useState<McpCatalogItem[]>([]);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState("");
  const [coreOnline, setCoreOnline] = useState(false);
  const [view, setView] = useState<View>("dashboard");
  const [providerId, setProviderId] = useState("");
  const [activeConversation, setActiveConversation] = useState<string | null>(null);
  const [theme, setTheme] = useState<string>(readTheme);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [coreUrlDraft, setCoreUrlDraft] = useState(getCoreUrl());

  const load = useCallback(async () => {
    const next = await api.get<Bootstrap>("/api/bootstrap");
    setBoot(next);
    setCoreOnline(true);
    setBootError("");
    setProviderId((current) => {
      const enabled = next.providers.filter((p) => p.enabled);
      if (current && enabled.some((p) => p.id === current)) return current;
      return enabled.find((p) => p.is_default)?.id || enabled[0]?.id || "";
    });
    const items = await api.get<McpCatalogItem[]>("/api/mcp/catalog").catch(() => []);
    setCatalog(items);
  }, []);

  // Initial boot: the desktop shell may still be spawning the Python core.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (let attempt = 0; attempt < 40; attempt += 1) {
        if (cancelled) return;
        try {
          await load();
          if (cancelled) return;
          if (!localStorage.getItem(THEME_KEY)) {
            const stored = await api.get<Settings>("/api/settings").catch(() => null);
            if (stored && (stored.theme === "dark" || stored.theme === "light")) setTheme(stored.theme);
          }
          setBooting(false);
          return;
        } catch (err) {
          if (attempt === 39) {
            setBootError((err as Error).message || "Could not reach the core.");
            setCoreOnline(false);
          } else {
            await new Promise((resolve) => setTimeout(resolve, 600));
          }
        }
      }
      if (!cancelled) setBooting(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  // Keep a light health pulse so the sidebar tells the truth.
  useEffect(() => {
    if (!boot) return;
    const timer = setInterval(async () => {
      try {
        await api.get("/api/health");
        setCoreOnline(true);
      } catch {
        setCoreOnline(false);
      }
    }, 15000);
    return () => clearInterval(timer);
  }, [boot]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }

  function startNewChat() {
    setActiveConversation(null);
    setView("chat");
    setMobileOpen(false);
  }

  async function deleteChat(id: string) {
    await api.del(`/api/conversations/${id}`);
    if (activeConversation === id) setActiveConversation(null);
    await load().catch(() => undefined);
  }

  function connect() {
    const clean = coreUrlDraft.trim().replace(/\/$/, "");
    if (!/^https?:\/\//.test(clean)) {
      setBootError("Core URL must start with http:// or https://");
      return;
    }
    setCoreUrl(clean);
    setBootError("");
    setBooting(true);
    load()
      .then(() => setBooting(false))
      .catch((err: Error) => {
        setBootError(err.message || "Still unreachable.");
        setBooting(false);
      });
  }

  if (booting) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4" style={{ background: "var(--bg)" }}>
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl text-white" style={{ background: "var(--accent)" }}>
          <Sparkles size={22} />
        </span>
        <div className="text-center">
          <h1 className="font-display text-2xl">AI-TRADER</h1>
          <p className="mt-1 flex items-center justify-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
            <Spinner size={12} /> starting the local core…
          </p>
        </div>
      </div>
    );
  }

  if (!boot) {
    return (
      <div className="flex h-full items-center justify-center p-6" style={{ background: "var(--bg)" }}>
        <div className="card w-full max-w-md p-6">
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl" style={{ background: "var(--panel)", color: "var(--err)" }}>
            <WifiOff size={18} />
          </div>
          <h1 className="font-display text-xl">Core offline</h1>
          <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
            The interface could not reach the Python core. Start it with{" "}
            <code className="rounded px-1 py-0.5 text-[11px]" style={{ background: "var(--code)" }}>py -3.12 core/main.py</code>{" "}
            or point the app at another machine.
          </p>
          {bootError && (
            <div className="mt-3 flex items-start gap-2 rounded-lg px-3 py-2 text-[11px]" style={{ background: "color-mix(in srgb, var(--err) 8%, transparent)", color: "var(--err)" }}>
              <AlertTriangle size={12} className="mt-0.5" /> {bootError}
            </div>
          )}
          <label className="label mt-4">Core URL</label>
          <input
            className="input font-mono text-xs"
            value={coreUrlDraft}
            onChange={(e) => setCoreUrlDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && connect()}
            placeholder="http://127.0.0.1:8765"
          />
          <div className="mt-4 flex gap-2">
            <button
              className="btn btn-primary flex-1"
              onClick={() => {
                setBooting(true);
                load()
                  .then(() => setBooting(false))
                  .catch((err: Error) => {
                    setBootError(err.message);
                    setBooting(false);
                  });
              }}
            >
              <RefreshCw size={14} /> Retry
            </button>
            <button className="btn" onClick={connect}>Use this URL</button>
          </div>
        </div>
      </div>
    );
  }

  const pendingApprovals = boot.approvals?.length || 0;

  let body: ReactNode;
  switch (view) {
    case "dashboard":
      body = <DashboardView accounts={boot.accounts} providers={boot.providers} onRefresh={load} />;
      break;
    case "models":
      body = <ModelsView providers={boot.providers} refresh={load} system={boot.system} />;
      break;
    case "mcp":
      body = (
        <McpView
          servers={boot.mcp}
          catalog={catalog}
          refresh={load}
          system={{ node: boot.system.node, uv: boot.system.uv }}
        />
      );
      break;
    case "skills":
      body = <SkillsView skills={boot.skills} refresh={load} />;
      break;
    case "brokers":
      body = (
        <BrokersView
          accounts={boot.accounts}
          catalog={boot.broker_catalog}
          settings={boot.settings}
          system={boot.system}
          refresh={load}
        />
      );
      break;
    case "trades":
      body = <TradesView accounts={boot.accounts} onRefresh={load} />;
      break;
    case "settings":
      body = (
        <SettingsView
          settings={boot.settings}
          system={boot.system}
          theme={theme}
          onTheme={setTheme}
          refresh={load}
        />
      );
      break;
    default:
      body = (
        <ChatView
          providers={boot.providers}
          accounts={boot.accounts}
          settings={boot.settings}
          providerId={providerId}
          setProviderId={setProviderId}
          activeConversation={activeConversation}
          setActiveConversation={setActiveConversation}
          refresh={load}
          onOpenView={(next) => setView(next)}
          onOpenSidebar={() => setMobileOpen(true)}
        />
      );
  }

  return (
    <div className="flex h-full" style={{ background: "var(--bg)" }}>
      <Sidebar
        view={view}
        setView={setView}
        conversations={boot.conversations}
        activeConversation={activeConversation}
        onNewChat={startNewChat}
        onSelectChat={(id) => {
          setActiveConversation(id);
          setView("chat");
          setMobileOpen(false);
        }}
        onDeleteChat={deleteChat}
        system={boot.system}
        theme={theme}
        onToggleTheme={toggleTheme}
        pendingApprovals={pendingApprovals}
        coreOnline={coreOnline}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        {view !== "chat" && (
          <div className="flex items-center gap-2 border-b px-3 py-2 md:hidden" style={{ borderColor: "var(--border)" }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setMobileOpen(true)}>
              <Menu size={16} />
            </button>
            <span className="text-sm font-medium">{VIEW_TITLES[view]}</span>
          </div>
        )}
        {!coreOnline && (
          <div className="flex items-center justify-center gap-2 px-3 py-1.5 text-[11px]" style={{ background: "color-mix(in srgb, var(--warn) 12%, transparent)", color: "var(--warn)" }}>
            <WifiOff size={12} /> Core connection lost — retrying. Orders cannot be sent.
          </div>
        )}
        <div className="min-h-0 flex-1">{body}</div>
      </main>
    </div>
  );
}
