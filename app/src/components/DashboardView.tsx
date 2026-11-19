import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Cpu,
  History,
  Layers,
  ListOrdered,
  Play,
  RefreshCw,
  Settings2,
  ShieldAlert,
  Square,
  Target,
  TrendingDown,
  TrendingUp,
  Wallet,
  Zap,
} from "lucide-react";
import type { Account, DashboardPayload, Decision, Position, Provider } from "../lib/types";
import { api, fmtMoney, timeAgo } from "../lib/api";
import { Empty, Field, Spinner, StatusDot, Toggle, useToast } from "./ui";

function num(value: unknown, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function strList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function fmtPrice(value: unknown): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed === 0) return "—";
  return parsed.toLocaleString("en-US", { maximumFractionDigits: 5 });
}

function fmtCountdown(seconds: number): string {
  if (seconds <= 0) return "now";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

function actionChip(action: string): string {
  if (action === "BUY") return "chip chip-ok";
  if (action === "SELL") return "chip chip-err";
  if (action === "CLOSE") return "chip chip-accent";
  return "chip";
}

function statusChip(status: string): string {
  if (["executed", "filled"].includes(status)) return "chip chip-ok";
  if (["pending_approval", "held", "approved"].includes(status)) return "chip chip-warn";
  if (["blocked", "failed", "error"].includes(status)) return "chip chip-err";
  return "chip";
}

function stageLabel(stage: string): string {
  return (
    {
      starting: "Starting",
      connecting: "Connecting to broker",
      scanning: "Scanning market",
      analysing: "Analysing",
      "asking models": "Asking models",
      executing: "Placing order",
      "managing exits": "Managing exits",
      waiting: "Waiting for next cycle",
      halted: "Halted",
      error: "Error",
      stopped: "Stopped",
    }[stage] || stage
  );
}

export function DashboardView({
  accounts,
  providers,
  onRefresh,
}: {
  accounts: Account[];
  providers: Provider[];
  onRefresh: () => Promise<void>;
}) {
  const { push } = useToast();
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [tab, setTab] = useState<"decisions" | "trades">("decisions");
  const [expanded, setExpanded] = useState("");
  const [nowTick, setNowTick] = useState(Date.now());
  const hydrated = useRef(false);

  const [intervalSec, setIntervalSec] = useState(300);
  const [execution, setExecution] = useState("auto");
  const [symbols, setSymbols] = useState("EURUSD, XAUUSD, BTCUSD");
  const [confidence, setConfidence] = useState(0.55);
  const [maxTrades, setMaxTrades] = useState(6);
  const [perCycle, setPerCycle] = useState(2);
  const [providerIds, setProviderIds] = useState<string[]>([]);
  const [accountId, setAccountId] = useState("");
  const [allowLiveAuto, setAllowLiveAuto] = useState(false);
  const [autostart, setAutostart] = useState(false);

  const load = useCallback(async (spinner = false) => {
    if (spinner) setLoading(true);
    try {
      const next = await api.get<DashboardPayload>("/api/dashboard");
      setData(next);
      if (!hydrated.current) {
        const c = next.control;
        setIntervalSec(num(c.autopilot_interval_sec, 300));
        setExecution(String(c.autopilot_execution || "auto"));
        const watch = strList(c.autopilot_symbols);
        setSymbols((watch.length ? watch : strList(c.default_symbols)).join(", "));
        setConfidence(num(c.autopilot_confidence, 0.55));
        setMaxTrades(num(c.autopilot_max_trades_per_day, 6));
        setPerCycle(num(c.autopilot_symbols_per_cycle, 2));
        setProviderIds(strList(c.autopilot_provider_ids));
        setAccountId(String(c.default_account_id || next.account.id || ""));
        setAllowLiveAuto(Boolean(c.autopilot_allow_live_auto));
        setAutostart(Boolean(c.autopilot_autostart));
        hydrated.current = true;
      }
    } catch (err) {
      if (spinner) push((err as Error).message, "error");
    } finally {
      if (spinner) setLoading(false);
    }
  }, [push]);

  useEffect(() => {
    void load();
    const poll = setInterval(() => void load(), 5000);
    const tick = setInterval(() => setNowTick(Date.now()), 1000);
    return () => {
      clearInterval(poll);
      clearInterval(tick);
    };
  }, [load]);

  function configBody() {
    const parsed = symbols
      .split(/[,\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    return {
      autopilot_interval_sec: intervalSec,
      autopilot_execution: execution,
      autopilot_symbols: parsed,
      autopilot_confidence: confidence,
      autopilot_max_trades_per_day: maxTrades,
      autopilot_symbols_per_cycle: perCycle,
      autopilot_provider_ids: providerIds,
      autopilot_allow_live_auto: allowLiveAuto,
      autopilot_autostart: autostart,
      default_account_id: accountId || "",
    };
  }

  async function saveConfig(silent = false) {
    await api.put("/api/settings", configBody());
    await onRefresh();
    await load();
    if (!silent) push("Autopilot configuration saved.");
  }

  async function start() {
    setBusy("start");
    try {
      await saveConfig(true);
      await api.post("/api/autopilot/start", { account_id: accountId || undefined });
      push("Autopilot started. It will analyse and trade the watchlist on its own.");
      await load();
      await onRefresh();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setBusy("");
    }
  }

  async function stop() {
    setBusy("stop");
    try {
      await api.post("/api/autopilot/stop");
      push("Autopilot stopped. Open positions are unchanged.", "info");
      await load();
      await onRefresh();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setBusy("");
    }
  }

  async function runOnce() {
    setBusy("once");
    try {
      await saveConfig(true);
      const res = await api.post<{ ok: boolean; error?: string }>("/api/autopilot/run-once");
      if (res.ok) push("One autopilot cycle completed.");
      else push(res.error || "Cycle failed.", "error");
      await load();
      await onRefresh();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setBusy("");
    }
  }

  async function kill() {
    if (!confirm("Pull the kill switch? Autopilot stops and all new orders are blocked.")) return;
    setBusy("kill");
    try {
      await api.post("/api/autopilot/kill");
      push("Kill switch is on. New orders are blocked.", "info");
      await load();
      await onRefresh();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setBusy("");
    }
  }

  async function resetKillSwitch() {
    setBusy("kill");
    try {
      await api.put("/api/settings", { kill_switch: false });
      push("Kill switch reset. Autopilot stays stopped until you press Start.");
      await load();
      await onRefresh();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setBusy("");
    }
  }

  async function closePosition(position: Position) {
    if (!confirm(`Close ${position.side} ${position.volume} ${position.symbol}?`)) return;
    const res = await api.post<{ ok: boolean; error?: string }>(`/api/positions/${position.ticket}/close`, {
      account_id: position.account_id || data?.account.id,
      symbol: position.symbol,
    });
    if (res.ok) push("Close request sent.");
    else push(res.error || "Close failed", "error");
    await load();
    await onRefresh();
  }

  if (!data) {
    return (
      <div className="flex h-full items-center justify-center text-sm" style={{ color: "var(--muted)" }}>
        {loading ? <Spinner size={18} /> : "Dashboard unavailable."}
      </div>
    );
  }

  const a = data.autopilot;
  const stats = data.stats;
  const snapshot = data.account.snapshot;
  const equity = num(snapshot.equity, 0);
  const balance = num(snapshot.balance, 0);
  const floating = num(snapshot.floating_pnl, 0);
  const nextIn = a.running && a.next_run_at ? Math.max(0, Math.round(a.next_run_at - nowTick / 1000)) : null;
  const stage = `${stageLabel(a.stage)}${a.symbol ? ` · ${a.symbol}` : ""}`;
  const killSwitch = Boolean(data.control.kill_switch);
  const enabledProviders = providers.filter((p) => p.enabled);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-5 py-6 md:px-8">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl">Autopilot dashboard</h1>
            <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
              What the models, bot and brokers are doing right now — plus the full decision history.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn" onClick={() => void load(true)} disabled={loading}>
              {loading ? <Spinner /> : <RefreshCw size={14} />} Refresh
            </button>
            <button className="btn" onClick={() => void saveConfig()} disabled={Boolean(busy)}>
              <Settings2 size={14} /> Save config
            </button>
            {a.running ? (
              <button className="btn btn-sm btn-danger" onClick={() => void stop()} disabled={Boolean(busy)}>
                {busy === "stop" ? <Spinner /> : <Square size={12} />} Stop
              </button>
            ) : (
              <button className="btn btn-primary" onClick={() => void start()} disabled={Boolean(busy) || killSwitch}>
                {busy === "start" ? <Spinner /> : <Play size={14} />} Start autopilot
              </button>
            )}
          </div>
        </div>

        {/* Live status */}
        <section className="card mb-4 overflow-hidden">
          <div className="flex flex-wrap items-center gap-3 border-b px-4 py-3" style={{ borderColor: "var(--border)" }}>
            <span className={`flex h-9 w-9 items-center justify-center rounded-xl ${a.running ? "animate-pulse" : ""}`}
              style={{ background: a.running ? "var(--accent-soft)" : "var(--panel)", color: a.running ? "var(--accent)" : "var(--muted)" }}>
              <Bot size={18} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="font-display text-lg">{a.running ? "Autopilot is running" : "Autopilot is stopped"}</h2>
                <span className={`chip ${a.running ? "chip-ok" : "chip-warn"}`}>
                  <StatusDot status={a.running ? "running" : "stopped"} /> {a.running ? "live" : "idle"}
                </span>
                {killSwitch && <span className="chip chip-err"><ShieldAlert size={10} /> kill switch</span>}
              </div>
              <p className="mt-0.5 text-xs" style={{ color: "var(--muted)" }}>
                {a.running ? stage : a.halted_reason || a.last_error || "Press Start to let the models trade on their own."}
                {nextIn !== null && <> · next cycle in <b>{fmtCountdown(nextIn)}</b></>}
                {a.cycle > 0 && <> · cycle #{a.cycle}</>}
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <button className="btn btn-sm" onClick={() => void runOnce()} disabled={Boolean(busy) || a.running}>
                {busy === "once" ? <Spinner /> : <Zap size={11} />} Run one cycle
              </button>
              {killSwitch ? (
                <button className="btn btn-sm" onClick={() => void resetKillSwitch()} disabled={Boolean(busy)}>
                  Reset kill switch
                </button>
              ) : (
                <button className="btn btn-sm btn-danger" onClick={() => void kill()} disabled={Boolean(busy)}>
                  {busy === "kill" ? <Spinner /> : <ShieldAlert size={11} />} Kill switch
                </button>
              )}
            </div>
          </div>

          <div className="grid gap-3 px-4 py-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <div className="label">Models voting</div>
              <div className="flex flex-wrap gap-1">
                {a.using_models.length === 0 && <span style={{ color: "var(--muted)" }}>default model</span>}
                {a.using_models.map((m) => <span key={m} className="chip chip-accent"><Cpu size={9} /> {m}</span>)}
              </div>
            </div>
            <div>
              <div className="label">Last decision</div>
              {a.last_decision ? (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-semibold">{a.last_decision.symbol}</span>
                  <span className={actionChip(a.last_decision.action)}>{a.last_decision.action}</span>
                  <span className="chip">{Math.round(a.last_decision.confidence * 100)}%</span>
                  <span className={statusChip(a.last_decision.status)}>{a.last_decision.status.replace("_", " ")}</span>
                  <span style={{ color: "var(--muted)" }}>{timeAgo(a.last_decision.ts)}</span>
                </div>
              ) : (
                <span style={{ color: "var(--muted)" }}>No decisions yet.</span>
              )}
            </div>
            <div>
              <div className="label">Risk posture</div>
              <div className="flex flex-wrap gap-1.5">
                <span className="chip">risk {num(data.control.max_risk_per_trade_pct, 1)}%</span>
                <span className="chip">max {num(data.control.max_open_positions, 2)} open</span>
                <span className="chip">daily {num(data.control.max_daily_loss_pct, 2)}%</span>
                <span className="chip">{String(data.control.trading_mode || "paper")}</span>
              </div>
            </div>
            <div>
              <div className="label">Account</div>
              <div className="truncate">
                <span className="font-medium">{data.account.name || "—"}</span>
                <span style={{ color: "var(--muted)" }}> · {data.account.broker || "no broker"} · {data.account.environment || "—"}</span>
              </div>
            </div>
          </div>
          {a.last_error && a.running && (
            <div className="mx-4 mb-3 rounded-lg px-3 py-2 text-[11px]" style={{ background: "color-mix(in srgb, var(--warn) 10%, transparent)", color: "var(--warn)" }}>
              Last error: {a.last_error}
            </div>
          )}
        </section>

        {/* KPIs */}
        <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-6">
          <Kpi icon={<Wallet size={14} />} label="Equity" value={fmtMoney(equity)} />
          <Kpi icon={<Layers size={14} />} label="Balance" value={fmtMoney(balance)} />
          <Kpi icon={stats.today_pnl >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />} label="Today P&L"
            value={fmtMoney(stats.today_pnl)} tone={stats.today_pnl >= 0 ? "ok" : "err"} sub={`${floating >= 0 ? "+" : ""}${fmtMoney(floating)} floating`} />
          <Kpi icon={<Target size={14} />} label="Total P&L" value={fmtMoney(stats.total_pnl)} tone={stats.total_pnl >= 0 ? "ok" : "err"} sub={`${stats.closed_trades} closed`} />
          <Kpi icon={<Activity size={14} />} label="Open positions" value={String(data.positions.length)} sub={`${stats.trades_today} trades today`} />
          <Kpi icon={<TrendingUp size={14} />} label="Win rate" value={`${stats.win_rate}%`} sub={`PF ${stats.profit_factor}`} />
        </div>

        {/* Equity curve */}
        <section className="card mb-4 p-4">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <TrendingUp size={14} style={{ color: "var(--accent)" }} /> Equity curve
            </div>
            <span className="text-[11px]" style={{ color: "var(--muted)" }}>
              {data.equity.length} points · recorded each cycle
            </span>
          </div>
          <EquityChart points={data.equity} />
        </section>

        {/* Configuration */}
        <section className="card mb-4 p-4">
          <div className="mb-3 flex items-center gap-2">
            <Settings2 size={15} style={{ color: "var(--accent)" }} />
            <h2 className="font-display text-lg">How it trades</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Account">
              <select className="select" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
                <option value="">Auto (prefers paper)</option>
                {accounts.map((acc) => (
                  <option key={acc.id} value={acc.id}>{acc.name} · {acc.environment}</option>
                ))}
              </select>
            </Field>
            <Field label="Execution" hint="Live always waits for approval unless the live switch below is on.">
              <select className="select" value={execution} onChange={(e) => setExecution(e.target.value)}>
                <option value="auto">Hands-free · execute automatically</option>
                <option value="approval">Ask me · create an approval</option>
              </select>
            </Field>
            <Field label="Cycle interval">
              <select className="select" value={intervalSec} onChange={(e) => setIntervalSec(Number(e.target.value))}>
                <option value={60}>Every 1 minute</option>
                <option value={300}>Every 5 minutes</option>
                <option value={900}>Every 15 minutes</option>
                <option value={1800}>Every 30 minutes</option>
                <option value={3600}>Every hour</option>
              </select>
            </Field>
            <Field label="Watchlist" hint="Comma separated. The risk gate allows these symbols too.">
              <input className="input" value={symbols} onChange={(e) => setSymbols(e.target.value)} placeholder="EURUSD, XAUUSD, BTCUSD" />
            </Field>
            <Field label="Symbols per cycle" hint="Rotates through the watchlist to limit model calls.">
              <input className="input" type="number" min={1} max={10} value={perCycle} onChange={(e) => setPerCycle(Number(e.target.value))} />
            </Field>
            <Field label="Max trades per day">
              <input className="input" type="number" min={1} max={100} value={maxTrades} onChange={(e) => setMaxTrades(Number(e.target.value))} />
            </Field>
            <Field label={`Confidence gate · ${Math.round(confidence * 100)}%`} hint="Below this the model votes are recorded as HOLD." className="sm:col-span-2">
              <input className="w-full" type="range" min={0.3} max={0.95} step={0.05} value={confidence} onChange={(e) => setConfidence(Number(e.target.value))} />
            </Field>
            <Field label="Voting models" hint="Pick up to 3. Empty means the default model." className="lg:col-span-3">
              <div className="flex flex-wrap gap-1.5">
                <button
                  className="chip"
                  style={providerIds.length === 0 ? { background: "var(--accent-soft)", color: "var(--accent)" } : undefined}
                  onClick={() => setProviderIds([])}
                >
                  Default model
                </button>
                {enabledProviders.map((p) => {
                  const active = providerIds.includes(p.id);
                  return (
                    <button
                      key={p.id}
                      className="chip"
                      title={`${p.model}${p.has_key ? "" : " · no key"}`}
                      style={active ? { background: "var(--accent-soft)", color: "var(--accent)" } : undefined}
                      onClick={() => setProviderIds((prev) => (active ? prev.filter((id) => id !== p.id) : [...prev, p.id]))}
                    >
                      {active && <Check size={9} />} {p.name}
                    </button>
                  );
                })}
              </div>
            </Field>
          </div>
          <div className="mt-3 grid gap-1 border-t pt-2 sm:grid-cols-2" style={{ borderColor: "var(--border)" }}>
            <Toggle checked={autostart} onChange={setAutostart} label="Resume after core restart"
              hint="Keeps the operator's on/off intent across app restarts." />
            <Toggle checked={allowLiveAuto} onChange={setAllowLiveAuto} label="Allow live auto-execution"
              hint="Only works with Allow live trading. Leave off until demo results are proven." danger />
          </div>
        </section>

        {/* History + side panels */}
        <div className="grid gap-4 lg:grid-cols-3">
          <section className="card overflow-hidden lg:col-span-2">
            <div className="flex items-center gap-2 border-b px-4 py-2.5" style={{ borderColor: "var(--border)" }}>
              <button
                className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium"
                style={tab === "decisions" ? { background: "var(--panel)" } : { color: "var(--muted)" }}
                onClick={() => setTab("decisions")}
              >
                <History size={12} /> Decisions
              </button>
              <button
                className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium"
                style={tab === "trades" ? { background: "var(--panel)" } : { color: "var(--muted)" }}
                onClick={() => setTab("trades")}
              >
                <ListOrdered size={12} /> Trades
              </button>
              <span className="ml-auto text-[11px]" style={{ color: "var(--muted)" }}>
                {tab === "decisions" ? `${data.decisions.length} records` : `${data.closed_positions.length} closed`}
              </span>
            </div>

            {tab === "decisions" && (
              <div className="max-h-[560px] overflow-y-auto">
                {data.decisions.length === 0 && (
                  <Empty icon={<Bot size={20} />} title="No decisions yet" body="Press Start or Run one cycle. Every model vote and risk-gate result is recorded here." />
                )}
                {data.decisions.map((d) => (
                  <DecisionRow
                    key={d.id}
                    decision={d}
                    expanded={expanded === d.id}
                    onToggle={() => setExpanded(expanded === d.id ? "" : d.id)}
                  />
                ))}
              </div>
            )}

            {tab === "trades" && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead style={{ background: "var(--panel)" }}>
                    <tr>{["Closed", "Symbol", "Side", "Volume", "P&L", "Note"].map((h) => <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {data.closed_positions.map((p, i) => {
                      const pnl = num(p.pnl, 0);
                      return (
                        <tr key={`${p.ticket}-${i}`} className="border-t" style={{ borderColor: "var(--border)" }}>
                          <td className="px-3 py-2" style={{ color: "var(--muted)" }}>{timeAgo(num(p.closed_at, 0))}</td>
                          <td className="px-3 py-2 font-medium">{String(p.symbol || "")}</td>
                          <td className="px-3 py-2" style={{ color: String(p.side) === "BUY" ? "var(--ok)" : "var(--err)" }}>{String(p.side || "")}</td>
                          <td className="px-3 py-2">{String(p.volume || "")}</td>
                          <td className="px-3 py-2 font-medium" style={{ color: pnl >= 0 ? "var(--ok)" : "var(--err)" }}>{fmtMoney(pnl)}</td>
                          <td className="max-w-[220px] truncate px-3 py-2" style={{ color: "var(--muted)" }} title={String(p.note || "")}>{String(p.note || "")}</td>
                        </tr>
                      );
                    })}
                    {data.closed_positions.length === 0 && <tr><td colSpan={6} className="px-3 py-8 text-center" style={{ color: "var(--muted)" }}>No closed positions on this account yet.</td></tr>}
                  </tbody>
                </table>
                <div className="border-t px-4 py-2 text-[11px]" style={{ borderColor: "var(--border)", color: "var(--muted)" }}>
                  Recent orders
                </div>
                <table className="w-full text-xs">
                  <tbody>
                    {data.orders.slice(0, 8).map((o) => (
                      <tr key={o.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                        <td className="px-3 py-2" style={{ color: "var(--muted)" }}>{timeAgo(o.created_at)}</td>
                        <td className="px-3 py-2 font-medium">{o.symbol}</td>
                        <td className="px-3 py-2" style={{ color: o.side === "BUY" ? "var(--ok)" : "var(--err)" }}>{o.side}</td>
                        <td className="px-3 py-2">{o.volume}</td>
                        <td className="px-3 py-2"><span className={statusChip(o.status)}>{o.status}</span></td>
                        <td className="px-3 py-2 font-mono text-[10px]" style={{ color: "var(--muted)" }}>{o.ticket || "—"}</td>
                      </tr>
                    ))}
                    {data.orders.length === 0 && <tr><td className="px-3 py-6 text-center" style={{ color: "var(--muted)" }}>No orders yet.</td></tr>}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <div className="space-y-4">
            <section className="card p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <Layers size={14} style={{ color: "var(--accent)" }} /> Open positions
                <span className="chip ml-auto">{data.positions.length}</span>
              </div>
              {data.positions.length === 0 ? (
                <p className="py-4 text-center text-xs" style={{ color: "var(--muted)" }}>Flat. No exposure right now.</p>
              ) : (
                <div className="space-y-2">
                  {data.positions.map((p) => (
                    <div key={p.ticket} className="rounded-lg px-2.5 py-2" style={{ background: "var(--panel)" }}>
                      <div className="flex flex-wrap items-center gap-1.5 text-xs">
                        <span className="font-semibold">{p.symbol}</span>
                        <span className={p.side === "BUY" ? "chip chip-ok" : "chip chip-err"}>{p.side}</span>
                        <span className="chip">{p.volume}</span>
                        <span className="ml-auto font-medium" style={{ color: Number(p.pnl) >= 0 ? "var(--ok)" : "var(--err)" }}>{fmtMoney(p.pnl)}</span>
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-[10px]" style={{ color: "var(--muted)" }}>
                        <span>entry {fmtPrice(p.entry)}</span>
                        <span>now {fmtPrice(p.price)}</span>
                        <span>SL {fmtPrice(p.sl)}</span>
                        <span>TP {fmtPrice(p.tp)}</span>
                        <button className="ml-auto underline" onClick={() => void closePosition(p)}>close</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="card p-4">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <Activity size={14} style={{ color: "var(--accent)" }} /> Bot activity
              </div>
              <div className="space-y-1.5">
                {data.activity.map((row, i) => (
                  <div key={`${row.ts}-${i}`} className="flex items-start gap-2 text-[11px]">
                    <StatusDot status={row.action.includes("error") || row.action.includes("failed") ? "error" : "ok"} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate font-mono">{row.action}</span>
                        <span className="ml-auto shrink-0" style={{ color: "var(--muted)" }}>{timeAgo(row.ts)}</span>
                      </div>
                      {row.detail && <p className="truncate" style={{ color: "var(--muted)" }} title={row.detail}>{row.detail}</p>}
                    </div>
                  </div>
                ))}
                {data.activity.length === 0 && <p className="py-3 text-center text-xs" style={{ color: "var(--muted)" }}>No activity yet.</p>}
              </div>
            </section>

            <section className="card p-4 text-[11px]" style={{ color: "var(--muted)" }}>
              <div className="mb-1 flex items-center gap-1.5 font-semibold" style={{ color: "var(--text)" }}>
                <Clock size={12} /> How the loop works
              </div>
              Each cycle: check exits → fetch quotes and candles → ask the voting models for JSON BUY/SELL/HOLD → average
              confidence → size from the risk budget → pass the hard risk gate → execute or queue approval → log the
              decision. No model can bypass the gate, and the kill switch always wins.
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

function Kpi({
  icon,
  label,
  value,
  sub,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  tone?: "ok" | "err";
}) {
  return (
    <div className="card p-3">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.1em]" style={{ color: "var(--muted)" }}>
        {icon} {label}
      </div>
      <div className="mt-1 font-display text-lg" style={{ color: tone === "ok" ? "var(--ok)" : tone === "err" ? "var(--err)" : "var(--text)" }}>
        {value}
      </div>
      {sub && <div className="text-[10px]" style={{ color: "var(--muted)" }}>{sub}</div>}
    </div>
  );
}

function EquityChart({ points }: { points: { ts: number; equity: number }[] }) {
  if (points.length < 2) {
    return (
      <div className="flex h-[120px] items-center justify-center text-xs" style={{ background: "var(--panel)", color: "var(--muted)", borderRadius: 8 }}>
        Equity points appear after the first autopilot cycle.
      </div>
    );
  }
  const values = points.map((p) => Number(p.equity));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 640;
  const h = 130;
  const pad = 6;
  const step = (w - pad * 2) / (values.length - 1);
  const coords = values.map((v, i) => [pad + i * step, h - pad - ((v - min) / span) * (h - pad * 2)]);
  const line = coords.map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L ${w - pad} ${h - pad} L ${pad} ${h - pad} Z`;
  const up = values[values.length - 1] >= values[0];
  const color = up ? "var(--ok)" : "var(--err)";
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height: 130 }} preserveAspectRatio="none">
        <path d={area} fill="color-mix(in srgb, var(--accent) 10%, transparent)" />
        <path d={line} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="mt-1 flex justify-between text-[10px]" style={{ color: "var(--muted)" }}>
        <span>{fmtMoney(min)}</span>
        <span>{timeAgo(points[0].ts)} → now</span>
        <span>{fmtMoney(max)}</span>
      </div>
    </div>
  );
}

function DecisionRow({
  decision,
  expanded,
  onToggle,
}: {
  decision: Decision;
  expanded: boolean;
  onToggle: () => void;
}) {
  const pnl = Number(decision.pnl || 0);
  return (
    <div className="border-t px-4 py-3" style={{ borderColor: "var(--border)" }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px]" style={{ color: "var(--muted)" }}>{timeAgo(decision.ts)}</span>
        <span className="text-sm font-semibold">{decision.symbol}</span>
        <span className={actionChip(decision.action)}>{decision.action}</span>
        <span className="chip">{Math.round(Number(decision.confidence || 0) * 100)}%</span>
        <span className={statusChip(decision.status)}>{decision.status.replace("_", " ")}</span>
        {decision.price ? <span className="text-[10px]" style={{ color: "var(--muted)" }}>@ {fmtPrice(decision.price)}</span> : null}
        {pnl !== 0 && <span className="text-[11px] font-medium" style={{ color: pnl >= 0 ? "var(--ok)" : "var(--err)" }}>{fmtMoney(pnl)}</span>}
        <span className="ml-auto max-w-[45%] truncate text-[10px]" style={{ color: "var(--muted)" }} title={decision.model}>{decision.model || "rules"}</span>
      </div>
      <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--muted)" }}>{decision.reason}</p>
      <div className="mt-1 flex flex-wrap items-center gap-3 text-[10px]" style={{ color: "var(--muted)" }}>
        <button className="flex items-center gap-1" onClick={onToggle}>
          {expanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />} model votes ({decision.votes.length})
        </button>
        {decision.risk_usd > 0 && <span>risk {fmtMoney(decision.risk_usd)}</span>}
        {decision.order_id && <span className="font-mono">{decision.order_id}</span>}
      </div>
      {expanded && (
        <div className="mt-2 space-y-1">
          {decision.votes.map((vote, i) => (
            <div key={`${vote.provider_id || vote.model}-${i}`} className="rounded-md px-2.5 py-1.5 text-[11px]" style={{ background: "var(--panel)" }}>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium">{vote.name || vote.model || "model"}</span>
                {vote.ok ? (
                  <>
                    <span className={actionChip(vote.action)}>{vote.action}</span>
                    <span className="chip">{Math.round(Number(vote.confidence || 0) * 100)}%</span>
                    {vote.latency_ms ? <span style={{ color: "var(--muted)" }}>{vote.latency_ms} ms</span> : null}
                  </>
                ) : (
                  <span className="chip chip-err">failed</span>
                )}
              </div>
              <p className="mt-0.5" style={{ color: "var(--muted)" }}>{vote.ok ? vote.reason : vote.error}</p>
            </div>
          ))}
          {decision.votes.length === 0 && <p className="text-[11px]" style={{ color: "var(--muted)" }}>No model votes recorded.</p>}
        </div>
      )}
    </div>
  );
}
