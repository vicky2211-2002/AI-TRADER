import {
  MessagesSquare,
  Cpu,
  Plug,
  BookOpen,
  Wallet,
  CandlestickChart,
  Settings,
  Plus,
  Trash2,
  Sun,
  Moon,
  ShieldCheck,
  Wifi,
  WifiOff,
  X,
  Sparkles,
  LayoutDashboard,
} from "lucide-react";
import type { Conversation, SystemInfo } from "../lib/types";
import { timeAgo } from "../lib/api";

export type View =
  | "dashboard"
  | "chat"
  | "models"
  | "mcp"
  | "skills"
  | "brokers"
  | "trades"
  | "settings";

const NAV: { id: View; label: string; icon: typeof MessagesSquare }[] = [
  { id: "dashboard", label: "Autopilot", icon: LayoutDashboard },
  { id: "chat", label: "Chat", icon: MessagesSquare },
  { id: "models", label: "Models", icon: Cpu },
  { id: "mcp", label: "MCP servers", icon: Plug },
  { id: "skills", label: "Skills", icon: BookOpen },
  { id: "brokers", label: "Brokers", icon: Wallet },
  { id: "trades", label: "Trades & risk", icon: CandlestickChart },
];

export function Sidebar({
  view,
  setView,
  conversations,
  activeConversation,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  system,
  theme,
  onToggleTheme,
  pendingApprovals,
  coreOnline,
  mobileOpen,
  onCloseMobile,
}: {
  view: View;
  setView: (v: View) => void;
  conversations: Conversation[];
  activeConversation: string | null;
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  system: SystemInfo | null;
  theme: string;
  onToggleTheme: () => void;
  pendingApprovals: number;
  coreOnline: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0 z-30 bg-black/30 md:hidden" onClick={onCloseMobile} />
      )}
      <aside
        className={`fixed z-40 flex h-full w-[268px] flex-col border-r transition-transform md:static md:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{ background: "var(--panel)", borderColor: "var(--border)" }}
      >
        <div className="flex items-center justify-between px-4 pt-4 pb-3">
          <button className="flex items-center gap-2.5 text-left" onClick={() => setView("chat")}>
            <span
              className="flex h-8 w-8 items-center justify-center rounded-lg text-white"
              style={{ background: "var(--accent)" }}
            >
              <Sparkles size={16} />
            </span>
            <span>
              <span className="block font-display text-[15px] leading-tight">AI-TRADER</span>
              <span className="block text-[10px] uppercase tracking-[0.14em]" style={{ color: "var(--muted)" }}>
                trading cockpit
              </span>
            </span>
          </button>
          <button className="btn btn-ghost btn-sm md:hidden" onClick={onCloseMobile}>
            <X size={15} />
          </button>
        </div>

        <div className="px-3 pb-2">
          <button className="btn btn-primary w-full" onClick={onNewChat}>
            <Plus size={15} /> New chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 pb-3">
          {view === "chat" && (
            <div className="mb-4">
              <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em]" style={{ color: "var(--muted)" }}>
                Recent
              </div>
              {conversations.length === 0 && (
                <p className="px-2 py-2 text-xs" style={{ color: "var(--muted)" }}>No conversations yet.</p>
              )}
              {conversations.slice(0, 12).map((c) => (
                <div key={c.id} className="group relative">
                  <button
                    className="nav-item pr-7"
                    style={activeConversation === c.id ? { background: "var(--card)", color: "var(--text)" } : undefined}
                    onClick={() => onSelectChat(c.id)}
                    title={c.title}
                  >
                    <MessagesSquare size={14} className="flex-shrink-0" />
                    <span className="truncate">{c.title}</span>
                    <span className="ml-auto text-[9px]" style={{ color: "var(--muted)" }}>{timeAgo(c.updated_at)}</span>
                  </button>
                  <button
                    className="absolute right-1.5 top-1/2 hidden -translate-y-1/2 rounded p-1 group-hover:block"
                    style={{ color: "var(--muted)" }}
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteChat(c.id);
                    }}
                    title="Delete conversation"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em]" style={{ color: "var(--muted)" }}>
            Workspace
          </div>
          {NAV.filter((n) => n.id !== "chat").map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                className={`nav-item ${view === item.id ? "active" : ""}`}
                onClick={() => {
                  setView(item.id);
                  onCloseMobile();
                }}
              >
                <Icon size={15} />
                <span>{item.label}</span>
                {item.id === "trades" && pendingApprovals > 0 && (
                  <span className="ml-auto chip chip-accent !py-0 !px-1.5">{pendingApprovals}</span>
                )}
              </button>
            );
          })}

          <button
            className={`nav-item ${view === "settings" ? "active" : ""}`}
            onClick={() => {
              setView("settings");
              onCloseMobile();
            }}
          >
            <Settings size={15} />
            <span>Settings</span>
          </button>
        </div>

        <div className="border-t px-3 py-3" style={{ borderColor: "var(--border)" }}>
          <div className="mb-2 flex items-center gap-2 px-1 text-[11px]" style={{ color: "var(--muted)" }}>
            {coreOnline ? <Wifi size={12} style={{ color: "var(--ok)" }} /> : <WifiOff size={12} style={{ color: "var(--err)" }} />}
            <span>{coreOnline ? "Core online" : "Core offline"}</span>
            <span className="ml-auto">v{system?.version || "0.1.0"}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 text-[11px]" style={{ color: "var(--muted)" }}>
              <ShieldCheck size={12} /> {system?.mt5_available ? "MT5 ready" : "MT5 n/a"}
            </span>
            <button className="btn btn-ghost btn-sm ml-auto" onClick={onToggleTheme} title="Toggle theme">
              {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
