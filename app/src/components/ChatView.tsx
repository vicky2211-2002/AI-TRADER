import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowUp,
  Square,
  Sparkles,
  Wrench,
  ChevronDown,
  ChevronRight,
  ShieldAlert,
  Check,
  X,
  TrendingUp,
  Newspaper,
  Calculator,
  Wallet,
  Menu,
  AlertTriangle,
} from "lucide-react";
import type { Account, Approval, ChatEvent, Message, Order, Provider, RiskCheck, Settings } from "../lib/types";
import { api, fmtMoney, streamChat } from "../lib/api";
import { RiskBadge, Spinner, useToast } from "./ui";

const SUGGESTIONS = [
  { icon: TrendingUp, title: "Analyse EURUSD", body: "Read the 4h structure, give me levels and invalidation." },
  { icon: Newspaper, title: "What moved gold today?", body: "Check news, DXY and XAUUSD levels." },
  { icon: Calculator, title: "Size a trade", body: "Risk 0.5% on GBPUSD with a 30-pip stop." },
  { icon: Wallet, title: "Review my positions", body: "Check open risk and whether any position should be trimmed." },
];

export function ChatView({
  providers,
  accounts,
  settings,
  providerId,
  setProviderId,
  activeConversation,
  setActiveConversation,
  refresh,
  onOpenView,
  onOpenSidebar,
}: {
  providers: Provider[];
  accounts: Account[];
  settings: Settings;
  providerId: string;
  setProviderId: (id: string) => void;
  activeConversation: string | null;
  setActiveConversation: (id: string | null) => void;
  refresh: () => Promise<void>;
  onOpenView: (view: "models" | "brokers" | "trades") => void;
  onOpenSidebar: () => void;
}) {
  const { push } = useToast();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"analyse" | "trade" | "ask">("analyse");
  const [sending, setSending] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [accountId, setAccountId] = useState<string>(accounts[0]?.id || "");
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const enabledProviders = providers.filter((p) => p.enabled);
  const provider = enabledProviders.find((p) => p.id === providerId) || enabledProviders[0];

  useEffect(() => {
    if (!providerId && enabledProviders[0]) setProviderId(enabledProviders[0].id);
  }, [providerId, enabledProviders, setProviderId]);

  useEffect(() => {
    if (!accountId && accounts[0]) setAccountId(accounts[0].id);
  }, [accounts, accountId]);

  const loadApprovals = useCallback(async () => {
    try {
      const [a, o] = await Promise.all([
        api.get<Approval[]>("/api/approvals"),
        api.get<Order[]>("/api/orders?limit=60"),
      ]);
      setApprovals(a);
      setOrders(o);
    } catch {
      /* core may be starting */
    }
  }, []);

  useEffect(() => {
    loadApprovals();
  }, [loadApprovals]);

  useEffect(() => {
    if (!activeConversation) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    api
      .get<Message[]>(`/api/conversations/${activeConversation}/messages`)
      .then((rows) => {
        if (cancelled) return;
        setMessages(
          rows.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            created_at: m.created_at,
            trace: (m.meta?.trace as Message["trace"]) || [],
          })),
        );
      })
      .catch(() => setMessages([]));
    return () => {
      cancelled = true;
    };
  }, [activeConversation]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, thinking, approvals]);

  const pendingOrders = useMemo(() => {
    const fromApprovals = new Set<string>();
    for (const a of approvals) {
      try {
        const payload = JSON.parse(a.payload_json);
        if (payload.order_id) fromApprovals.add(payload.order_id);
      } catch {
        /* noop */
      }
    }
    return orders.filter((o) => o.status === "pending_approval" && fromApprovals.has(o.id));
  }, [approvals, orders]);

  const otherApprovals = approvals.filter((a) => a.kind !== "order");

  async function send(text?: string) {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    if (!provider) {
      push("Add and test a model first (Models).", "error");
      return;
    }
    setError("");
    setInput("");
    setSending(true);
    setThinking(true);
    const userMsg: Message = { id: `local-u-${Date.now()}`, role: "user", content };
    const assistantId = `local-a-${Date.now()}`;
    setMessages((prev) => [...prev, userMsg, { id: assistantId, role: "assistant", content: "", trace: [], streaming: true }]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        {
          message: content,
          conversation_id: activeConversation,
          provider_id: provider.id,
          account_id: accountId || null,
          mode,
        },
        (event: ChatEvent) => {
          if (event.type === "tool_start") {
            setThinking(true);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, trace: [...(m.trace || []), { name: event.name || "", args: event.args || {}, result: {} }] }
                  : m,
              ),
            );
          } else if (event.type === "tool_result") {
            setMessages((prev) =>
              prev.map((m) => {
                if (m.id !== assistantId) return m;
                const trace = [...(m.trace || [])];
                for (let i = trace.length - 1; i >= 0; i -= 1) {
                  if (trace[i].name === event.name && Object.keys(trace[i].result || {}).length === 0) {
                    trace[i] = { ...trace[i], result: event.result || {} };
                    break;
                  }
                }
                return { ...m, trace };
              }),
            );
          } else if (event.type === "text") {
            setThinking(false);
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, content: event.text || "" } : m)),
            );
          } else if (event.type === "error") {
            setThinking(false);
            setError(event.message || "Model error");
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: m.content || `**Provider error:** ${event.message || "unknown"}` }
                  : m,
              ),
            );
          } else if (event.type === "done") {
            if (event.conversation_id) setActiveConversation(event.conversation_id);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: event.text ?? m.content, trace: event.trace || m.trace, streaming: false }
                  : m,
              ),
            );
            setSending(false);
            setThinking(false);
            refresh();
            loadApprovals();
          }
        },
        controller.signal,
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError((err as Error).message);
        push((err as Error).message, "error");
      }
    } finally {
      setSending(false);
      setThinking(false);
      abortRef.current = null;
    }
  }

  async function approveOrder(order: Order) {
    try {
      const result = await api.post<{ ok?: boolean; error?: string }>(`/api/orders/${order.id}/approve`);
      if (result.error) push(result.error, "error");
      else push(`Order ${result.ok ? "sent to broker" : "processed"}.`, "ok");
      await loadApprovals();
      await refresh();
    } catch (err) {
      push((err as Error).message, "error");
    }
  }

  async function rejectOrder(order: Order) {
    await api.post(`/api/orders/${order.id}/reject`, { reason: "Rejected in chat" });
    await loadApprovals();
    push("Order rejected.", "info");
  }

  async function approveOther(id: string) {
    try {
      const result = await api.post<{ ok?: boolean; error?: string; text?: string }>(`/api/approvals/${id}/approve`);
      if (result.error) push(result.error, "error");
      else push(result.text ? `Approved: ${result.text.slice(0, 120)}` : "Action executed.", "ok");
      await loadApprovals();
    } catch (err) {
      push((err as Error).message, "error");
    }
  }

  const riskPct = Number(settings.max_risk_per_trade_pct ?? 1);
  const hasProviders = enabledProviders.length > 0;

  return (
    <div className="flex h-full flex-col" style={{ background: "var(--bg)" }}>
      {/* header */}
      <div className="flex items-center gap-2 border-b px-3 py-2.5 md:px-6" style={{ borderColor: "var(--border)" }}>
        <button className="btn btn-ghost btn-sm md:hidden" onClick={onOpenSidebar}>
          <Menu size={16} />
        </button>
        <div className="relative">
          <select
            className="select !w-auto max-w-[260px] !py-1.5 !pl-2.5 !pr-7 text-xs font-medium"
            value={provider?.id || ""}
            onChange={(e) => setProviderId(e.target.value)}
          >
            {enabledProviders.length === 0 && <option value="">No model configured</option>}
            {enabledProviders.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.model}
              </option>
            ))}
          </select>
        </div>
        {provider && (
          <span className={`chip ${provider.last_status === "ok" ? "chip-ok" : provider.has_key || provider.base_url.includes("localhost") ? "" : "chip-warn"}`}>
            {provider.last_status === "ok" ? `${provider.last_latency_ms} ms` : provider.has_key || provider.base_url.includes("localhost") ? "untested" : "no key"}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1 rounded-lg p-0.5" style={{ background: "var(--panel)", border: "1px solid var(--border)" }}>
          {(["analyse", "trade", "ask"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className="rounded-md px-2.5 py-1 text-[11px] font-medium capitalize transition-colors"
              style={mode === m ? { background: "var(--card)", color: "var(--text)", boxShadow: "var(--shadow)" } : { color: "var(--muted)" }}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      {/* messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-6 md:px-6">
          {messages.length === 0 && (
            <div className="pt-6 fade-in">
              <div
                className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl text-white"
                style={{ background: "var(--accent)" }}
              >
                <Sparkles size={20} />
              </div>
              <h1 className="font-display text-3xl leading-tight">Good to see you.</h1>
              <p className="mt-1.5 text-sm" style={{ color: "var(--muted)" }}>
                Markets first, orders second. I analyse, size the risk, and every ticket waits for your yes.
              </p>
              {!hasProviders && (
                <div className="mt-4 card flex items-start gap-3 p-4" style={{ borderColor: "var(--warn)" }}>
                  <AlertTriangle size={17} style={{ color: "var(--warn)", marginTop: 2 }} />
                  <div className="text-sm">
                    <p className="font-medium">No model provider yet</p>
                    <p className="mt-0.5" style={{ color: "var(--muted)" }}>
                      Connect a free API (Google, Groq, Cerebras, OpenRouter) or local Ollama, then test it.
                    </p>
                    <button className="btn btn-primary btn-sm mt-2.5" onClick={() => onOpenView("models")}>
                      Connect a model
                    </button>
                  </div>
                </div>
              )}
              <div className="mt-5 grid gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => {
                  const Icon = s.icon;
                  return (
                    <button
                      key={s.title}
                      className="card p-3.5 text-left transition-transform hover:-translate-y-0.5"
                      onClick={() => send(`${s.title}. ${s.body}`)}
                      disabled={!hasProviders}
                    >
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <Icon size={14} style={{ color: "var(--accent)" }} /> {s.title}
                      </div>
                      <p className="mt-1 text-xs leading-relaxed" style={{ color: "var(--muted)" }}>{s.body}</p>
                    </button>
                  );
                })}
              </div>
              <div className="mt-5 flex flex-wrap gap-1.5 text-[11px]" style={{ color: "var(--muted)" }}>
                <span className="chip">Paper mode</span>
                <span className="chip">{riskPct}% risk / trade</span>
                <span className="chip">approval required</span>
                <span className="chip">demo-only by default</span>
              </div>
            </div>
          )}

          {messages.map((m, idx) =>
            m.role === "user" ? (
              <div key={m.id || idx} className="mb-5 flex justify-end fade-in">
                <div
                  className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md px-4 py-2.5 text-sm"
                  style={{ background: "var(--panel-2)", border: "1px solid var(--border)" }}
                >
                  {m.content}
                </div>
              </div>
            ) : (
              <div key={m.id || idx} className="mb-6 fade-in">
                <div className="mb-1.5 flex items-center gap-2">
                  <span
                    className="flex h-6 w-6 items-center justify-center rounded-md text-white"
                    style={{ background: "var(--accent)" }}
                  >
                    <Sparkles size={12} />
                  </span>
                  <span className="text-xs font-medium">AI-TRADER</span>
                  {m.streaming && sending && (
                    <span className="flex items-center gap-1 text-[11px]" style={{ color: "var(--muted)" }}>
                      working
                      <span className="typing-dot">.</span>
                      <span className="typing-dot">.</span>
                      <span className="typing-dot">.</span>
                    </span>
                  )}
                </div>
                {m.trace && m.trace.length > 0 && (
                  <div className="mb-2 space-y-1.5">
                    {m.trace.map((t, i) => (
                      <ToolCard key={`${t.name}-${i}`} name={t.name} args={t.args} result={t.result} />
                    ))}
                  </div>
                )}
                {m.content ? (
                  <div className="prose-chat">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  </div>
                ) : (
                  thinking && (
                    <div className="flex items-center gap-2 py-1 text-xs" style={{ color: "var(--muted)" }}>
                      <Spinner /> thinking
                    </div>
                  )
                )}
              </div>
            ),
          )}

          {thinking && !messages.some((m) => m.role === "assistant" && m.content) && !sending && (
            <div className="flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
              <Spinner /> thinking
            </div>
          )}

          {/* approvals */}
          {(pendingOrders.length > 0 || otherApprovals.length > 0) && (
            <div className="mt-3 space-y-2">
              {pendingOrders.map((o) => (
                <div key={o.id} className="card overflow-hidden fade-in" style={{ borderColor: "var(--accent)" }}>
                  <div className="flex items-center gap-2 px-4 py-2.5" style={{ background: "var(--accent-soft)" }}>
                    <ShieldAlert size={15} style={{ color: "var(--accent)" }} />
                    <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--accent)" }}>
                      Approval required
                    </span>
                    <span className="ml-auto text-[11px]" style={{ color: "var(--muted)" }}>expires when you decide</span>
                  </div>
                  <div className="px-4 py-3">
                    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                      <span className="font-display text-lg">{o.side} {o.volume} {o.symbol}</span>
                      <span className="text-xs" style={{ color: "var(--muted)" }}>{o.account_id}</span>
                      <span className="chip chip-accent">risk {fmtMoney(o.risk_usd)} ({o.risk_pct}%)</span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-1 text-xs sm:grid-cols-4">
                      <div><span style={{ color: "var(--muted)" }}>Entry </span>{o.price || "market"}</div>
                      <div><span style={{ color: "var(--muted)" }}>SL </span>{o.sl}</div>
                      <div><span style={{ color: "var(--muted)" }}>TP </span>{o.tp || "—"}</div>
                      <div><span style={{ color: "var(--muted)" }}>Type </span>{o.order_type}</div>
                    </div>
                    {o.reason && <p className="mt-2 text-xs italic" style={{ color: "var(--muted)" }}>{o.reason}</p>}
                    <div className="mt-3 flex gap-2">
                      <button className="btn btn-primary btn-sm" onClick={() => approveOrder(o)}>
                        <Check size={13} /> Approve & send
                      </button>
                      <button className="btn btn-sm" onClick={() => rejectOrder(o)}>
                        <X size={13} /> Reject
                      </button>
                    </div>
                  </div>
                </div>
              ))}
              {otherApprovals.map((a) => (
                <div key={a.id} className="card p-3.5 fade-in">
                  <div className="flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--accent)" }}>
                    <ShieldAlert size={14} /> {a.kind.replace("_", " ")} approval
                  </div>
                  <pre className="mt-2 max-h-32 overflow-auto rounded p-2 text-[11px]" style={{ background: "var(--code)" }}>
                    {a.payload_json}
                  </pre>
                  <div className="mt-2 flex gap-2">
                    <button className="btn btn-primary btn-sm" onClick={() => approveOther(a.id)}>
                      <Check size={13} /> Approve
                    </button>
                    <button
                      className="btn btn-sm"
                      onClick={async () => {
                        await api.post(`/api/approvals/${a.id}/reject`);
                        await loadApprovals();
                      }}
                    >
                      <X size={13} /> Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {error && (
            <div className="mt-3 flex items-start gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: "color-mix(in srgb, var(--err) 8%, transparent)", color: "var(--err)" }}>
              <AlertTriangle size={13} className="mt-0.5" /> {error}
            </div>
          )}
          <div ref={bottomRef} className="h-2" />
        </div>
      </div>

      {/* composer */}
      <div className="border-t px-3 pb-3 pt-2.5 md:px-6" style={{ borderColor: "var(--border)" }}>
        <div className="mx-auto w-full max-w-3xl">
          <div
            className="card flex items-end gap-2 p-2 transition-shadow"
            style={{ borderRadius: 18 }}
          >
            <textarea
              ref={textareaRef}
              className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none"
              placeholder={hasProviders ? "Ask about a market, or say 'propose a trade on EURUSD'…" : "Connect a model to start"}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                const el = e.target as HTMLTextAreaElement;
                el.style.height = "auto";
                el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              disabled={sending}
              rows={1}
            />
            {sending ? (
              <button className="btn btn-sm !h-9 !w-9 !p-0" onClick={() => abortRef.current?.abort()} title="Stop">
                <Square size={14} />
              </button>
            ) : (
              <button
                className="btn btn-primary !h-9 !w-9 !p-0"
                onClick={() => send()}
                disabled={!input.trim() || !hasProviders}
                title="Send"
              >
                <ArrowUp size={16} />
              </button>
            )}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 px-1 text-[10px]" style={{ color: "var(--muted)" }}>
            <span>Enter to send · Shift+Enter for a new line</span>
            <span className="ml-auto flex items-center gap-1.5">
              <select
                className="bg-transparent text-[10px] outline-none"
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                title="Trading account"
              >
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.name} ({a.environment})</option>
                ))}
              </select>
              <span>·</span>
              <span>{riskPct}% risk</span>
              <span>·</span>
              <span>{settings.require_order_approval ? "approval on" : "auto-approve"}</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function ToolCard({
  name,
  args,
  result,
}: {
  name: string;
  args: Record<string, unknown>;
  result: Record<string, unknown>;
}) {
  const [open, setOpen] = useState(false);
  const done = Object.keys(result || {}).length > 0;
  const summary = useMemo(() => {
    if (!done) return "running…";
    const r = result as Record<string, unknown>;
    if (typeof r.error === "string") return `error: ${r.error}`;
    if (typeof r.price !== "undefined") return `price ${r.price}`;
    if (typeof r.text === "string") return `${r.text.slice(0, 90)}…`;
    if (Array.isArray(r.positions)) return `${r.positions.length} positions`;
    if (Array.isArray(r.orders)) return `${r.orders.length} orders`;
    if (r.status) return String(r.status);
    return "done";
  }, [done, result]);

  return (
    <div className="overflow-hidden rounded-lg text-xs" style={{ background: "var(--panel)", border: "1px solid var(--border)" }}>
      <button className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left" onClick={() => setOpen(!open)}>
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Wrench size={11} style={{ color: "var(--accent)" }} />
        <span className="font-mono text-[11px]">{name}</span>
        <span className="ml-auto truncate text-[10px]" style={{ color: "var(--muted)", maxWidth: "45%" }}>{summary}</span>
      </button>
      {open && (
        <div className="border-t px-2.5 py-2" style={{ borderColor: "var(--border)" }}>
          <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--muted)" }}>arguments</div>
          <pre className="mt-1 max-h-32 overflow-auto text-[10px]">{JSON.stringify(args, null, 2)}</pre>
          <div className="mt-2 text-[10px] uppercase tracking-wide" style={{ color: "var(--muted)" }}>result</div>
          <pre className="mt-1 max-h-48 overflow-auto text-[10px]">{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
