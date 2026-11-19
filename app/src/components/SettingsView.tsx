import { useEffect, useMemo, useState } from "react";
import {
  Save,
  ShieldAlert,
  Server,
  Palette,
  KeyRound,
  RotateCcw,
  Info,
  Lock,
  AlertTriangle,
  CheckCircle2,
  Cpu,
} from "lucide-react";
import type { Settings, SystemInfo } from "../lib/types";
import { api, getCoreUrl, getToken, setCoreUrl, setToken } from "../lib/api";
import { Field, Spinner, Toggle, useToast } from "./ui";

const MODES: { id: string; label: string; body: string; danger?: boolean }[] = [
  { id: "paper", label: "Paper", body: "Simulated fills inside the core. No broker credentials needed." },
  { id: "demo", label: "Demo", body: "Real broker demo account. Live prices, fake money." },
  { id: "live", label: "Live", body: "Real money. Requires the live-trading switch below.", danger: true },
];

export function SettingsView({
  settings,
  system,
  theme,
  onTheme,
  refresh,
}: {
  settings: Settings;
  system: SystemInfo;
  theme: string;
  onTheme: (theme: string) => void;
  refresh: () => Promise<void>;
}) {
  const { push } = useToast();
  const [draft, setDraft] = useState<Settings>(settings);
  const [symbols, setSymbols] = useState((settings.default_symbols || []).join(", "));
  const [saving, setSaving] = useState(false);
  const [coreUrl, setCoreUrlState] = useState(getCoreUrl());
  const [token, setTokenState] = useState(getToken());
  const [restarting, setRestarting] = useState(false);

  useEffect(() => {
    setDraft(settings);
    setSymbols((settings.default_symbols || []).join(", "));
  }, [settings]);

  const dirty = useMemo(() => {
    const keys: (keyof Settings)[] = [
      "trading_mode",
      "allow_live_trading",
      "require_order_approval",
      "kill_switch",
      "max_risk_per_trade_pct",
      "max_daily_loss_pct",
      "max_drawdown_pct",
      "max_open_positions",
      "max_lot_size",
      "max_spread_points",
      "auto_execute_tools",
    ];
    return keys.some((k) => String(draft[k]) !== String(settings[k]));
  }, [draft, settings]);

  function patch<K extends keyof Settings>(key: K, value: Settings[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  async function save() {
    setSaving(true);
    try {
      const parsedSymbols = symbols
        .split(/[,\s]+/)
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);
      const body: Record<string, unknown> = {
        trading_mode: draft.trading_mode,
        allow_live_trading: Boolean(draft.allow_live_trading),
        require_order_approval: Boolean(draft.require_order_approval),
        kill_switch: Boolean(draft.kill_switch),
        max_risk_per_trade_pct: Number(draft.max_risk_per_trade_pct),
        max_daily_loss_pct: Number(draft.max_daily_loss_pct),
        max_drawdown_pct: Number(draft.max_drawdown_pct),
        max_open_positions: Number(draft.max_open_positions),
        max_lot_size: Number(draft.max_lot_size),
        max_spread_points: Number(draft.max_spread_points),
        auto_execute_tools: Boolean(draft.auto_execute_tools),
        default_symbols: parsedSymbols.length ? parsedSymbols : ["EURUSD"],
      };
      const next = await api.put<Settings>("/api/settings", body);
      setDraft(next);
      await refresh();
      push("Settings saved. The risk gate uses them on the next order.");
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  function applyCore() {
    const clean = coreUrl.trim().replace(/\/$/, "");
    if (!/^https?:\/\//.test(clean)) {
      push("Core URL must start with http:// or https://", "error");
      return;
    }
    setCoreUrl(clean);
    setToken(token.trim());
    push("Core connection updated — reloading.");
    setTimeout(() => window.location.reload(), 350);
  }

  async function restartCore() {
    const bridge = (window as unknown as { aiTrader?: { restartCore?: () => Promise<boolean> } }).aiTrader;
    if (!bridge?.restartCore) {
      push("Restart is only available in the desktop app.", "info");
      return;
    }
    setRestarting(true);
    try {
      const ok = await bridge.restartCore();
      push(ok ? "Core restarted." : "Core did not come back — check the log.", ok ? "ok" : "error");
      await refresh();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setRestarting(false);
    }
  }

  const liveBlocked = draft.trading_mode === "live" && !draft.allow_live_trading;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-5 py-6 md:px-8">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl">Settings</h1>
            <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
              Risk limits, trading mode and the local core connection.
            </p>
          </div>
          <button className="btn btn-primary" onClick={save} disabled={saving || !dirty || liveBlocked}>
            {saving ? <Spinner /> : <Save size={14} />} Save changes
          </button>
        </div>

        {/* Trading mode */}
        <section className="card mb-4 p-4">
          <div className="mb-3 flex items-center gap-2">
            <ShieldAlert size={15} style={{ color: "var(--accent)" }} />
            <h2 className="font-display text-lg">Trading mode</h2>
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            {MODES.map((m) => (
              <button
                key={m.id}
                className="rounded-xl border p-3 text-left transition-colors"
                style={
                  draft.trading_mode === m.id
                    ? {
                        borderColor: m.danger ? "var(--err)" : "var(--accent)",
                        background: m.danger ? "color-mix(in srgb, var(--err) 6%, transparent)" : "var(--accent-soft)",
                      }
                    : { borderColor: "var(--border)", background: "var(--bg)" }
                }
                onClick={() => patch("trading_mode", m.id)}
              >
                <div className="flex items-center gap-2 text-sm font-medium">
                  {draft.trading_mode === m.id && <CheckCircle2 size={13} style={{ color: m.danger ? "var(--err)" : "var(--accent)" }} />}
                  {m.label}
                </div>
                <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--muted)" }}>{m.body}</p>
              </button>
            ))}
          </div>

          <div className="mt-3 space-y-1 border-t pt-3" style={{ borderColor: "var(--border)" }}>
            <Toggle
              checked={Boolean(draft.allow_live_trading)}
              onChange={(v) => patch("allow_live_trading", v)}
              label="Allow live trading"
              hint="Hard switch for real money. Leave off until a demo account has passed your validation gate."
              danger
            />
            <Toggle
              checked={Boolean(draft.require_order_approval)}
              onChange={(v) => patch("require_order_approval", v)}
              label="Require approval for every order"
              hint="Recommended. Turning this off lets approved tool calls reach the broker without a second look."
            />
            <Toggle
              checked={Boolean(draft.kill_switch)}
              onChange={(v) => patch("kill_switch", v)}
              label="Kill switch"
              hint="Blocks all new orders immediately, in every mode."
              danger
            />
            <Toggle
              checked={Boolean(draft.auto_execute_tools)}
              onChange={(v) => patch("auto_execute_tools", v)}
              label="Auto-execute read-only MCP tools"
              hint="Only safe, read-only tools run without asking. Trading tools always require approval."
            />
          </div>

          {liveBlocked && (
            <div className="mt-3 flex items-start gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: "color-mix(in srgb, var(--err) 8%, transparent)", color: "var(--err)" }}>
              <AlertTriangle size={13} className="mt-0.5" />
              Enable “Allow live trading” before saving live mode.
            </div>
          )}
        </section>

        {/* Risk limits */}
        <section className="card mb-4 p-4">
          <div className="mb-3 flex items-center gap-2">
            <Lock size={15} style={{ color: "var(--accent)" }} />
            <h2 className="font-display text-lg">Risk limits</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Risk per trade (%)" hint="Size is capped at this fraction of equity.">
              <input
                className="input"
                type="number"
                min={0.05}
                max={50}
                step={0.05}
                value={Number(draft.max_risk_per_trade_pct)}
                onChange={(e) => patch("max_risk_per_trade_pct", Number(e.target.value))}
              />
            </Field>
            <Field label="Max daily loss (%)" hint="New entries halt for the day once this is hit.">
              <input
                className="input"
                type="number"
                min={0.05}
                max={50}
                step={0.1}
                value={Number(draft.max_daily_loss_pct)}
                onChange={(e) => patch("max_daily_loss_pct", Number(e.target.value))}
              />
            </Field>
            <Field label="Max drawdown (%)" hint="Peak-to-trough equity. Keeps the kill switch honest.">
              <input
                className="input"
                type="number"
                min={0.05}
                max={50}
                step={0.1}
                value={Number(draft.max_drawdown_pct)}
                onChange={(e) => patch("max_drawdown_pct", Number(e.target.value))}
              />
            </Field>
            <Field label="Max open positions">
              <input
                className="input"
                type="number"
                min={1}
                max={100}
                step={1}
                value={Number(draft.max_open_positions)}
                onChange={(e) => patch("max_open_positions", Number(e.target.value))}
              />
            </Field>
            <Field label="Max lot size" hint="Hard ceiling on any single order.">
              <input
                className="input"
                type="number"
                min={0.01}
                max={100}
                step={0.01}
                value={Number(draft.max_lot_size)}
                onChange={(e) => patch("max_lot_size", Number(e.target.value))}
              />
            </Field>
            <Field label="Max spread (points)" hint="Orders are rejected when the spread is wider.">
              <input
                className="input"
                type="number"
                min={1}
                max={100}
                step={1}
                value={Number(draft.max_spread_points)}
                onChange={(e) => patch("max_spread_points", Number(e.target.value))}
              />
            </Field>
            <Field label="Watchlist symbols" hint="Comma separated. Used for quotes and suggestions." className="sm:col-span-2">
              <input
                className="input"
                value={symbols}
                onChange={(e) => setSymbols(e.target.value)}
                placeholder="EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSD"
              />
            </Field>
          </div>
          <p className="mt-3 text-[11px]" style={{ color: "var(--muted)" }}>
            Risk checks run inside the core, not the UI. Editing the interface cannot bypass them.
          </p>
        </section>

        {/* Connection */}
        <section className="card mb-4 p-4">
          <div className="mb-3 flex items-center gap-2">
            <Server size={15} style={{ color: "var(--accent)" }} />
            <h2 className="font-display text-lg">Core connection</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Core URL" hint="Desktop: http://127.0.0.1:8765 · Android: your PC's LAN address.">
              <input className="input font-mono text-xs" value={coreUrl} onChange={(e) => setCoreUrlState(e.target.value)} />
            </Field>
            <Field label="Access token (optional)" hint="Set AI_TRADER_TOKEN on the core to require it.">
              <div className="relative">
                <KeyRound size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "var(--muted)" }} />
                <input
                  className="input pl-8 font-mono text-xs"
                  type="password"
                  value={token}
                  onChange={(e) => setTokenState(e.target.value)}
                  placeholder="not set"
                />
              </div>
            </Field>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn btn-sm" onClick={applyCore}>Apply connection</button>
            <button className="btn btn-sm" onClick={restartCore} disabled={restarting}>
              {restarting ? <Spinner size={12} /> : <RotateCcw size={12} />} Restart core
            </button>
          </div>
        </section>

        {/* Appearance */}
        <section className="card mb-4 p-4">
          <div className="mb-3 flex items-center gap-2">
            <Palette size={15} style={{ color: "var(--accent)" }} />
            <h2 className="font-display text-lg">Appearance</h2>
          </div>
          <div className="flex gap-2">
            {[
              { id: "light", label: "Light" },
              { id: "dark", label: "Dark" },
            ].map((t) => (
              <button
                key={t.id}
                className="btn btn-sm"
                style={
                  theme === t.id
                    ? { borderColor: "var(--accent)", background: "var(--accent-soft)", color: "var(--accent)" }
                    : undefined
                }
                onClick={() => onTheme(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px]" style={{ color: "var(--muted)" }}>
            Applied immediately and stored on this device. The sidebar toggle flips it too.
          </p>
        </section>

        {/* System */}
        <section className="card p-4">
          <div className="mb-3 flex items-center gap-2">
            <Cpu size={15} style={{ color: "var(--accent)" }} />
            <h2 className="font-display text-lg">System</h2>
          </div>
          <div className="grid gap-2 text-xs sm:grid-cols-2">
            {[
              ["App", `${system.app} v${system.version}`],
              ["Platform", `${system.platform} · ${system.machine}`],
              ["Python", system.python],
              ["Wordmark", "AI-TRADER"],
              ["Data dir", system.data_dir],
              ["Skills dir", system.skills_dir],
              ["Vault", system.vault],
              ["Core", `${system.host}:${system.port}`],
              ["MT5 bridge", system.mt5_available ? "available" : "not available on this OS"],
              ["Node / uv", `${system.node ? "node" : "—"} / ${system.uv ? "uv" : "—"}`],
            ].map(([k, v]) => (
              <div key={k} className="flex items-start justify-between gap-3 rounded-lg px-2.5 py-1.5" style={{ background: "var(--panel)" }}>
                <span style={{ color: "var(--muted)" }}>{k}</span>
                <span className="max-w-[60%] truncate text-right font-mono text-[11px]" title={String(v)}>{v}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-start gap-2 rounded-lg px-3 py-2 text-[11px]" style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>
            <Info size={13} className="mt-0.5 flex-shrink-0" />
            <span>
              API keys and broker passwords live in the local vault, encrypted with Fernet
              when the <code>cryptography</code> package is installed. They are never
              written to the repo, logs or chat transcripts.
            </span>
          </div>
        </section>
      </div>
    </div>
  );
}
