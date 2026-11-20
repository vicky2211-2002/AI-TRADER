import { useEffect, useState } from "react";
import { Wallet, Plus, Zap, Trash2, Pencil, RefreshCw, ShieldCheck, AlertTriangle, KeyRound, CheckCircle2 } from "lucide-react";
import type { Account, BrokerCatalogItem, Settings, SystemInfo } from "../lib/types";
import { api, fmtMoney } from "../lib/api";
import { Empty, Field, JsonBox, Modal, Spinner, StatusDot, Toggle, useToast } from "./ui";

export function BrokersView({
  accounts,
  catalog,
  settings,
  system,
  refresh,
}: {
  accounts: Account[];
  catalog: BrokerCatalogItem[];
  settings: Settings;
  system: SystemInfo;
  refresh: () => Promise<void>;
}) {
  const { push } = useToast();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Account | null>(null);
  const [busy, setBusy] = useState("");
  const [snapshots, setSnapshots] = useState<Record<string, Record<string, unknown> | null>>({});
  const [detail, setDetail] = useState<{ account: Account; data: Record<string, unknown> } | null>(null);

  async function test(account: Account) {
    setBusy(account.id);
    try {
      const res = await api.post<{ ok: boolean; error?: string; account?: Record<string, unknown> }>(`/api/accounts/${account.id}/test`);
      if (!res.ok) {
        push(res.error || "Connection failed", "error");
      } else {
        const snap = await api.get<Record<string, unknown>>(`/api/accounts/${account.id}/snapshot`);
        setSnapshots((prev) => ({ ...prev, [account.id]: snap }));
        push(`${account.name} connected — ${snap.trade_mode || "?"} · ${fmtMoney(snap.balance)}`);
      }
      await refresh();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setBusy("");
    }
  }

  async function loadSnapshot(account: Account) {
    try {
      const snap = await api.get<Record<string, unknown>>(`/api/accounts/${account.id}/snapshot`);
      setSnapshots((prev) => ({ ...prev, [account.id]: snap }));
      setDetail({ account, data: snap });
    } catch (err) {
      push((err as Error).message, "error");
    }
  }

  async function remove(account: Account) {
    if (!confirm(`Delete account "${account.name}"? Open broker positions are untouched.`)) return;
    await api.del(`/api/accounts/${account.id}`);
    await refresh();
    push("Account removed.", "info");
  }

  async function toggleKill(value: boolean) {
    await api.put("/api/settings", { kill_switch: value });
    await refresh();
    push(value ? "Kill switch ON — all orders are blocked." : "Kill switch off.", value ? "info" : "ok");
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-5 py-6 md:px-8">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl">Brokers</h1>
            <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
              Paper by default. MT5 for desktop, MetaAPI for macOS/Android, REST for everything else.
            </p>
          </div>
          <button className="btn btn-primary" onClick={() => setAdding(true)}><Plus size={14} /> Add account</button>
        </div>

        <div className="mb-4 grid gap-2 sm:grid-cols-3">
          <div className="soft px-3.5 py-2.5">
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--muted)" }}>Trading mode</div>
            <div className="mt-0.5 text-sm font-semibold capitalize">{settings.trading_mode}</div>
          </div>
          <div className="soft px-3.5 py-2.5">
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--muted)" }}>Risk per trade / daily</div>
            <div className="mt-0.5 text-sm font-semibold">{settings.max_risk_per_trade_pct}% / {settings.max_daily_loss_pct}%</div>
          </div>
          <div className="soft px-3.5 py-2.5">
            <Toggle
              checked={!!settings.kill_switch}
              onChange={toggleKill}
              danger
              label="Kill switch"
              hint={settings.kill_switch ? "All entries blocked" : "Armed and ready"}
            />
          </div>
        </div>

        {!system.mt5_available && (
          <div className="mb-3 flex items-start gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: "color-mix(in srgb, var(--warn) 10%, transparent)", color: "var(--warn)" }}>
            <AlertTriangle size={13} className="mt-0.5" />
            {system.platform === "Windows"
              ? "MetaTrader5 could not be loaded by this core. Reinstall AI-TRADER, or use the MetaAPI cloud bridge."
              : "Local MT5 needs Windows. On this platform use the MetaAPI cloud bridge (or CCXT / Alpaca / OANDA)."}
          </div>
        )}
        {system.mt5_available && (
          <div className="mb-3 flex items-start gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: "var(--panel)", color: "var(--muted)" }}>
            <CheckCircle2 size={13} className="mt-0.5" />
            MetaTrader5 bridge is bundled and ready. Add your broker login below — the terminal is detected automatically.
          </div>
        )}

        {accounts.length === 0 ? (
          <Empty icon={<Wallet size={20} />} title="No trading account" body="Start with the paper simulator — it needs no keys and cannot lose real money." />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {accounts.map((a) => {
              const snap = snapshots[a.id];
              return (
                <div key={a.id} className="card p-4">
                  <div className="flex items-start gap-2">
                    <StatusDot status={a.status === "connected" ? "connected" : a.status === "error" ? "error" : "idle"} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <h3 className="truncate text-sm font-semibold">{a.name}</h3>
                        <span className={`chip ${a.environment === "live" ? "chip-err" : a.environment === "demo" ? "chip-warn" : "chip-ok"}`}>
                          {a.environment.toUpperCase()}
                        </span>
                        <span className="chip">{a.broker}</span>
                        {a.has_secret && <span className="chip"><KeyRound size={9} /> stored</span>}
                      </div>
                      {snap && (
                        <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px]">
                          <span>Balance <b>{fmtMoney(snap.balance, String(snap.currency || "USD"))}</b></span>
                          <span>Equity <b>{fmtMoney(snap.equity, String(snap.currency || "USD"))}</b></span>
                          <span style={{ color: "var(--muted)" }}>{String(snap.trade_mode || "")}</span>
                        </div>
                      )}
                      {a.last_error && (
                        <p className="mt-1 rounded px-2 py-1 font-mono text-[10px]" style={{ background: "color-mix(in srgb, var(--err) 8%, transparent)", color: "var(--err)" }}>
                          {a.last_error}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <button className="btn btn-sm" onClick={() => test(a)} disabled={busy === a.id}>
                      {busy === a.id ? <Spinner /> : <Zap size={12} />} Test
                    </button>
                    <button className="btn btn-sm" onClick={() => loadSnapshot(a)}><RefreshCw size={12} /> Snapshot</button>
                    <button className="btn btn-sm" onClick={() => setEditing(a)}><Pencil size={12} /> Edit</button>
                    <button className="btn btn-sm btn-danger ml-auto" onClick={() => remove(a)}><Trash2 size={12} /></button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="mt-6 flex items-start gap-2 rounded-xl p-4 text-xs leading-relaxed" style={{ background: "var(--panel)", color: "var(--muted)" }}>
          <ShieldCheck size={15} className="mt-0.5 flex-shrink-0" />
          <span>
            Live is locked by two switches: the account environment and <b>Settings &gt; allow live trading</b>.
            Demo must pass 30 verified trades (PF ≥ 1.2) before you even consider enabling it. Nothing here is financial advice.
          </span>
        </div>
      </div>

      {(adding || editing) && (
        <AccountForm
          catalog={catalog}
          account={editing}
          onClose={() => {
            setAdding(false);
            setEditing(null);
          }}
          onSaved={async () => {
            setAdding(false);
            setEditing(null);
            await refresh();
          }}
        />
      )}

      {detail && (
        <Modal open onClose={() => setDetail(null)} wide title={detail.account.name} subtitle={`${detail.account.broker} · ${detail.account.environment}`}>
          <JsonBox value={detail.data} />
        </Modal>
      )}
    </div>
  );
}

function AccountForm({
  catalog,
  account,
  onClose,
  onSaved,
}: {
  catalog: BrokerCatalogItem[];
  account: Account | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { push } = useToast();
  const initialBroker = account?.broker || catalog[0]?.id || "paper";
  const [brokerId, setBrokerId] = useState(initialBroker);
  const [name, setName] = useState(account?.name || "My account");
  const [environment, setEnvironment] = useState(account?.environment || "paper");
  const [config, setConfig] = useState<Record<string, unknown>>(account?.config || {});
  const [secret, setSecret] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const broker = catalog.find((b) => b.id === brokerId) || catalog[0];

  useEffect(() => {
    if (!account) {
      const defaults: Record<string, unknown> = {};
      broker?.fields.forEach((f) => {
        if (f.default !== undefined) defaults[f.key] = f.default;
      });
      setConfig(defaults);
      setSecret({});
    }
  }, [brokerId, broker, account]);

  async function save() {
    setSaving(true);
    try {
      if (account) {
        await api.patch(`/api/accounts/${account.id}`, { name, environment, config, secret });
        push("Account updated.");
      } else {
        await api.post("/api/accounts", { name, broker: brokerId, environment, config, secret });
        push("Account added. Click Test to verify the connection.");
      }
      await onSaved();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} wide title={account ? "Edit account" : "Add trading account"} subtitle="Credentials are encrypted into the local vault.">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Account name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Broker">
          <select className="select" value={brokerId} onChange={(e) => setBrokerId(e.target.value)} disabled={!!account}>
            {catalog.map((b) => <option key={b.id} value={b.id}>{b.label}</option>)}
          </select>
        </Field>
        <Field label="Environment" hint="Live is gated behind Settings and a demo record.">
          <select className="select" value={environment} onChange={(e) => setEnvironment(e.target.value)}>
            {(broker?.environments || ["paper"]).filter((e) => e !== "live").map((e) => (
              <option key={e} value={e}>{e}</option>
            ))}
          </select>
        </Field>
        <div className="sm:col-span-2 rounded-lg p-3 text-[11px]" style={{ background: "var(--panel)", color: "var(--muted)" }}>
          {broker?.tagline}
        </div>

        {broker?.fields.map((field) => (
          <Field key={field.key} label={field.label} className={field.type === "textarea" ? "sm:col-span-2" : ""}>
            {field.type === "select" ? (
              <select
                className="select"
                value={String(config[field.key] ?? field.default ?? "")}
                onChange={(e) => setConfig({ ...config, [field.key]: e.target.value })}
              >
                {(field.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <input
                className="input"
                type={field.secret ? "password" : field.type === "number" ? "number" : "text"}
                placeholder={field.placeholder || (field.secret ? "stored encrypted" : "")}
                value={field.secret ? secret[field.key] ?? "" : String(config[field.key] ?? "")}
                onChange={(e) =>
                  field.secret
                    ? setSecret({ ...secret, [field.key]: e.target.value })
                    : setConfig({ ...config, [field.key]: field.type === "number" ? Number(e.target.value) : e.target.value })
                }
              />
            )}
          </Field>
        ))}
      </div>
      <div className="mt-4 flex items-start gap-2 text-[11px]" style={{ color: "var(--muted)" }}>
        <ShieldCheck size={13} className="mt-0.5" />
        Demo-first: a REAL MT5 account is refused while the environment is demo, and live is refused until you explicitly enable it in Settings.
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={save} disabled={saving || !name}>{saving && <Spinner />} {account ? "Save" : "Add account"}</button>
      </div>
    </Modal>
  );
}
