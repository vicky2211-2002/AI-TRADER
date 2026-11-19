import { useCallback, useEffect, useState } from "react";
import { ShieldAlert, Plus, Check, X, RefreshCw, History, ListOrdered, Layers, ScrollText } from "lucide-react";
import type { Account, Approval, Order, Position, RiskCheck } from "../lib/types";
import { api, fmtMoney, timeAgo } from "../lib/api";
import { Empty, Field, Modal, RiskBadge, Spinner, StatusDot, useToast } from "./ui";

type Tab = "approvals" | "orders" | "positions" | "audit";

export function TradesView({
  accounts,
  onRefresh,
}: {
  accounts: Account[];
  onRefresh: () => Promise<void>;
}) {
  const { push } = useToast();
  const [tab, setTab] = useState<Tab>("approvals");
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [audit, setAudit] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);
  const [newOrder, setNewOrder] = useState(false);
  const [checkResult, setCheckResult] = useState<{ order_id?: string; status: string; checks: RiskCheck[]; blocked_by: string[] } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [a, o, p, au] = await Promise.all([
        api.get<Approval[]>("/api/approvals"),
        api.get<Order[]>("/api/orders?limit=80"),
        api.get<{ positions: Position[] }>("/api/positions").catch(() => ({ positions: [] })),
        api.get<Record<string, unknown>[]>("/api/audit?limit=80").catch(() => []),
      ]);
      setApprovals(a);
      setOrders(o);
      setPositions(p.positions || []);
      setAudit(au);
    } catch {
      /* core starting */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(load, 12000);
    return () => clearInterval(timer);
  }, [load]);

  async function approveOrder(o: Order) {
    const res = await api.post<{ ok?: boolean; error?: string }>(`/api/orders/${o.id}/approve`);
    if (res.error) push(res.error, "error");
    else push(res.ok ? "Order sent to the broker." : "Processed.");
    await load();
    await onRefresh();
  }

  async function rejectOrder(o: Order) {
    await api.post(`/api/orders/${o.id}/reject`, { reason: "Rejected in Trades" });
    await load();
    push("Order rejected.", "info");
  }

  async function approveOther(a: Approval) {
    const res = await api.post<{ ok?: boolean; error?: string; text?: string }>(`/api/approvals/${a.id}/approve`);
    if (res.error) push(res.error, "error");
    else push(res.text ? res.text.slice(0, 120) : "Approved.");
    await load();
  }

  async function closePosition(p: Position) {
    if (!confirm(`Close ${p.side} ${p.volume} ${p.symbol} (ticket ${p.ticket})?`)) return;
    const res = await api.post<{ ok: boolean; error?: string }>(`/api/positions/${p.ticket}/close`, {
      account_id: p.account_id,
      symbol: p.symbol,
    });
    if (res.ok) push("Close request sent.");
    else push(res.error || "Close failed", "error");
    await load();
  }

  const pendingOrders = orders.filter((o) => o.status === "pending_approval");

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl px-5 py-6 md:px-8">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl">Trades &amp; risk</h1>
            <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
              Every ticket is risk-gated and needs your yes. Nothing here can bypass the limits.
            </p>
          </div>
          <div className="flex gap-2">
            <button className="btn" onClick={load} disabled={loading}>{loading ? <Spinner /> : <RefreshCw size={14} />} Refresh</button>
            <button className="btn btn-primary" onClick={() => setNewOrder(true)}><Plus size={14} /> New order</button>
          </div>
        </div>

        <div className="mb-4 flex flex-wrap gap-1 rounded-lg p-1" style={{ background: "var(--panel)", width: "fit-content" }}>
          {([
            ["approvals", "Approvals", ShieldAlert],
            ["orders", "Orders", ListOrdered],
            ["positions", "Positions", Layers],
            ["audit", "Audit", ScrollText],
          ] as const).map(([id, label, Icon]) => (
            <button
              key={id}
              className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium"
              style={tab === id ? { background: "var(--card)", boxShadow: "var(--shadow)" } : { color: "var(--muted)" }}
              onClick={() => setTab(id)}
            >
              <Icon size={12} /> {label}
              {id === "approvals" && approvals.length > 0 && <span className="chip chip-accent !py-0 !px-1.5">{approvals.length}</span>}
            </button>
          ))}
        </div>

        {tab === "approvals" && (
          <div className="space-y-2.5">
            {approvals.length === 0 && pendingOrders.length === 0 && (
              <Empty icon={<ShieldAlert size={20} />} title="Nothing waiting" body="Agent or manual orders that pass the risk gate appear here for approval." />
            )}
            {pendingOrders.map((o) => (
              <div key={o.id} className="card p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-lg">{o.side} {o.volume} {o.symbol}</span>
                  <span className="chip chip-accent">risk {fmtMoney(o.risk_usd)}</span>
                  <span className="chip">{o.risk_pct}%</span>
                  <span className="ml-auto text-[11px]" style={{ color: "var(--muted)" }}>{timeAgo(o.created_at)}</span>
                </div>
                <div className="mt-1.5 grid grid-cols-2 gap-1 text-xs sm:grid-cols-4">
                  <span><span style={{ color: "var(--muted)" }}>Entry </span>{o.price || "market"}</span>
                  <span><span style={{ color: "var(--muted)" }}>SL </span>{o.sl}</span>
                  <span><span style={{ color: "var(--muted)" }}>TP </span>{o.tp || "—"}</span>
                  <span><span style={{ color: "var(--muted)" }}>Account </span>{o.account_id}</span>
                </div>
                {o.reason && <p className="mt-1.5 text-xs italic" style={{ color: "var(--muted)" }}>{o.reason}</p>}
                <div className="mt-2.5 flex gap-2">
                  <button className="btn btn-primary btn-sm" onClick={() => approveOrder(o)}><Check size={12} /> Approve</button>
                  <button className="btn btn-sm" onClick={() => rejectOrder(o)}><X size={12} /> Reject</button>
                </div>
              </div>
            ))}
            {approvals.filter((a) => a.kind !== "order").map((a) => (
              <div key={a.id} className="card p-4">
                <div className="text-xs font-semibold" style={{ color: "var(--accent)" }}>{a.kind.replace("_", " ")}</div>
                <pre className="mt-1.5 max-h-28 overflow-auto rounded p-2 text-[11px]" style={{ background: "var(--code)" }}>{a.payload_json}</pre>
                <div className="mt-2 flex gap-2">
                  <button className="btn btn-primary btn-sm" onClick={() => approveOther(a)}><Check size={12} /> Approve</button>
                  <button
                    className="btn btn-sm"
                    onClick={async () => {
                      await api.post(`/api/approvals/${a.id}/reject`);
                      await load();
                    }}
                  >
                    <X size={12} /> Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === "orders" && (
          <div className="card overflow-x-auto">
            <table className="w-full text-xs">
              <thead style={{ background: "var(--panel)" }}>
                <tr>{["Time", "Symbol", "Side", "Vol", "Entry", "SL", "TP", "Risk", "Status", "Ticket"].map((h) => <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>)}</tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.id} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="px-3 py-2" style={{ color: "var(--muted)" }}>{timeAgo(o.created_at)}</td>
                    <td className="px-3 py-2 font-medium">{o.symbol}</td>
                    <td className="px-3 py-2" style={{ color: o.side === "BUY" ? "var(--ok)" : "var(--err)" }}>{o.side}</td>
                    <td className="px-3 py-2">{o.volume}</td>
                    <td className="px-3 py-2">{o.price || "mkt"}</td>
                    <td className="px-3 py-2">{o.sl || "—"}</td>
                    <td className="px-3 py-2">{o.tp || "—"}</td>
                    <td className="px-3 py-2">{fmtMoney(o.risk_usd)}</td>
                    <td className="px-3 py-2"><span className={`chip ${o.status === "filled" ? "chip-ok" : o.status === "blocked" || o.status === "failed" ? "chip-err" : "chip-warn"}`}>{o.status}</span></td>
                    <td className="px-3 py-2 font-mono text-[10px]" style={{ color: "var(--muted)" }}>{o.ticket || "—"}</td>
                  </tr>
                ))}
                {orders.length === 0 && <tr><td colSpan={10} className="px-3 py-8 text-center" style={{ color: "var(--muted)" }}>No orders yet.</td></tr>}
              </tbody>
            </table>
          </div>
        )}

        {tab === "positions" && (
          <div className="card overflow-x-auto">
            <table className="w-full text-xs">
              <thead style={{ background: "var(--panel)" }}>
                <tr>{["Ticket", "Symbol", "Side", "Volume", "Entry", "Price", "P&L", ""].map((h) => <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>)}</tr>
              </thead>
              <tbody>
                {positions.map((p) => (
                  <tr key={p.ticket} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="px-3 py-2 font-mono text-[10px]">{p.ticket.slice(0, 12)}</td>
                    <td className="px-3 py-2 font-medium">{p.symbol}</td>
                    <td className="px-3 py-2" style={{ color: p.side === "BUY" ? "var(--ok)" : "var(--err)" }}>{p.side}</td>
                    <td className="px-3 py-2">{p.volume}</td>
                    <td className="px-3 py-2">{p.entry}</td>
                    <td className="px-3 py-2">{p.price ?? "—"}</td>
                    <td className="px-3 py-2 font-medium" style={{ color: Number(p.pnl) >= 0 ? "var(--ok)" : "var(--err)" }}>{fmtMoney(p.pnl)}</td>
                    <td className="px-3 py-2"><button className="btn btn-sm" onClick={() => closePosition(p)}>Close</button></td>
                  </tr>
                ))}
                {positions.length === 0 && <tr><td colSpan={8} className="px-3 py-8 text-center" style={{ color: "var(--muted)" }}>No open positions on the selected account.</td></tr>}
              </tbody>
            </table>
          </div>
        )}

        {tab === "audit" && (
          <div className="card divide-y" style={{ borderColor: "var(--border)" }}>
            {audit.map((row, i) => (
              <div key={i} className="flex items-start gap-3 px-4 py-2.5 text-xs">
                <StatusDot status={String(row.action || "").includes("failed") ? "error" : "ok"} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px]">{String(row.action)}</span>
                    <span style={{ color: "var(--muted)" }}>{row.actor as string}</span>
                    <span className="ml-auto" style={{ color: "var(--muted)" }}>{timeAgo(Number(row.ts))}</span>
                  </div>
                  {row.detail ? <pre className="mt-0.5 line-clamp-2 whitespace-pre-wrap break-all text-[10px]" style={{ color: "var(--muted)" }}>{String(row.detail)}</pre> : null}
                </div>
              </div>
            ))}
            {audit.length === 0 && <div className="px-4 py-8 text-center text-xs" style={{ color: "var(--muted)" }}>No audit entries yet.</div>}
          </div>
        )}
      </div>

      {newOrder && (
        <OrderForm
          accounts={accounts}
          result={checkResult}
          onClose={() => {
            setNewOrder(false);
            setCheckResult(null);
          }}
          onResult={setCheckResult}
          onDone={async () => {
            await load();
            await onRefresh();
          }}
        />
      )}
    </div>
  );
}

function OrderForm({
  accounts,
  result,
  onClose,
  onResult,
  onDone,
}: {
  accounts: Account[];
  result: { status: string; checks: RiskCheck[]; blocked_by: string[]; order_id?: string } | null;
  onClose: () => void;
  onResult: (r: { status: string; checks: RiskCheck[]; blocked_by: string[]; order_id?: string }) => void;
  onDone: () => Promise<void>;
}) {
  const { push } = useToast();
  const [accountId, setAccountId] = useState(accounts[0]?.id || "");
  const [symbol, setSymbol] = useState("EURUSD");
  const [side, setSide] = useState("BUY");
  const [volume, setVolume] = useState("0.01");
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    setSaving(true);
    try {
      const res = await api.post<{ status: string; checks: RiskCheck[]; blocked_by: string[]; order_id?: string }>("/api/orders", {
        account_id: accountId,
        symbol,
        side,
        volume: Number(volume),
        sl: Number(sl || 0),
        tp: Number(tp || 0),
        reason,
      });
      onResult(res);
      if (res.status === "pending_approval") push("Passed the risk gate — approve it in the Approvals tab.");
      else if (res.status === "blocked") push("Blocked by the risk gate.", "error");
      else push(`Order ${res.status}.`);
      await onDone();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} wide title="New order" subtitle="Proposal only — the hard risk gate and your approval come next.">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Account">
          <select className="select" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            {accounts.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.environment})</option>)}
          </select>
        </Field>
        <Field label="Symbol"><input className="input" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} /></Field>
        <Field label="Side">
          <select className="select" value={side} onChange={(e) => setSide(e.target.value)}>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </Field>
        <Field label="Volume (lots)"><input className="input" type="number" step="0.01" value={volume} onChange={(e) => setVolume(e.target.value)} /></Field>
        <Field label="Stop loss (required)"><input className="input" type="number" step="0.00001" value={sl} onChange={(e) => setSl(e.target.value)} /></Field>
        <Field label="Take profit (optional)"><input className="input" type="number" step="0.00001" value={tp} onChange={(e) => setTp(e.target.value)} /></Field>
        <Field label="Reason" className="sm:col-span-2"><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Donchian breakout, 4h close above channel" /></Field>
      </div>

      {result && (
        <div className="mt-3 rounded-lg p-3" style={{ background: "var(--panel)" }}>
          <div className="mb-1 text-xs font-semibold">
            Risk gate: <span style={{ color: result.status === "blocked" ? "var(--err)" : "var(--ok)" }}>{result.status.toUpperCase()}</span>
          </div>
          {result.checks.map((c) => <RiskBadge key={c.label} label={c.label} ok={c.ok} detail={c.detail} />)}
          {result.blocked_by.length > 0 && (
            <p className="mt-1 text-[11px]" style={{ color: "var(--err)" }}>Blocked by: {result.blocked_by.join(", ")}</p>
          )}
        </div>
      )}

      <div className="mt-4 flex justify-end gap-2">
        <button className="btn" onClick={onClose}>Close</button>
        <button className="btn btn-primary" onClick={submit} disabled={saving || !sl}>{saving && <Spinner />} Run risk check &amp; propose</button>
      </div>
    </Modal>
  );
}
