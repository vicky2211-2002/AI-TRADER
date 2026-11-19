import { useState } from "react";
import {
  Plug,
  Plus,
  Play,
  Square,
  Zap,
  Pencil,
  Trash2,
  ChevronDown,
  ChevronRight,
  Download,
  Terminal,
  Globe,
  AlertTriangle,
} from "lucide-react";
import type { McpCatalogItem, McpServer, McpTool } from "../lib/types";
import { api } from "../lib/api";
import { Empty, Field, JsonBox, Modal, Spinner, StatusDot, Toggle, useToast } from "./ui";

type Draft = {
  serverId?: string;
  name: string;
  transport: string;
  command: string;
  args: string[];
  url: string;
  env: Record<string, string>;
  category: string;
  notes: string;
  enabled: boolean;
  auto_start: boolean;
};

export function McpView({
  servers,
  catalog,
  refresh,
  system,
}: {
  servers: McpServer[];
  catalog: McpCatalogItem[];
  refresh: () => Promise<void>;
  system: { node: boolean; uv: boolean };
}) {
  const { push } = useToast();
  const [tab, setTab] = useState<"installed" | "catalog">("installed");
  const [editing, setEditing] = useState<Draft | null>(null);
  const [busy, setBusy] = useState<string>("");
  const [expanded, setExpanded] = useState<string>("");
  const [callTool, setCallTool] = useState<{ server: McpServer; tool: McpTool } | null>(null);

  async function start(s: McpServer) {
    setBusy(s.id);
    try {
      const result = await api.post<{ ok: boolean; error?: string; tools?: McpTool[] }>(`/api/mcp/${s.id}/start`);
      if (result.ok) push(`${s.name} started — ${result.tools?.length || 0} tools.`);
      else push(`${s.name}: ${result.error}`, "error");
      await refresh();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setBusy("");
    }
  }

  async function stop(s: McpServer) {
    setBusy(s.id);
    await api.post(`/api/mcp/${s.id}/stop`);
    await refresh();
    setBusy("");
    push(`${s.name} stopped.`, "info");
  }

  async function test(s: McpServer) {
    setBusy(s.id);
    try {
      const result = await api.post<{ ok: boolean; error?: string; tools?: McpTool[]; stderr?: string }>(`/api/mcp/${s.id}/test`);
      if (result.ok) push(`${s.name}: ${result.tools?.length || 0} tools discovered.`);
      else push(`${s.name}: ${result.error}`, "error");
      await refresh();
    } finally {
      setBusy("");
    }
  }

  async function remove(s: McpServer) {
    if (!confirm(`Remove "${s.name}"? The process is stopped and the config deleted.`)) return;
    await api.del(`/api/mcp/${s.id}`);
    await refresh();
    push("MCP server removed.", "info");
  }

  function addFromCatalog(item: McpCatalogItem) {
    setEditing({
      serverId: undefined,
      name: item.name,
      transport: item.transport,
      command: item.command || "",
      args: item.args || [],
      url: item.url || "",
      env: item.env || {},
      category: item.category,
      notes: item.notes,
      enabled: true,
      auto_start: false,
    });
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-5 py-6 md:px-8">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl">MCP servers</h1>
            <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
              Give the agent real tools: browsers, scraping, docs, databases, exchange data.
            </p>
          </div>
          <div className="flex gap-1.5">
            <button className="btn" onClick={() => setEditing({ name: "", transport: "stdio", command: "npx", args: [], url: "", env: {}, category: "general", notes: "", enabled: true, auto_start: false })}>
              <Plus size={14} /> Custom server
            </button>
          </div>
        </div>

        <div className="mb-4 flex gap-1 rounded-lg p-1" style={{ background: "var(--panel)", width: "fit-content" }}>
          {(["installed", "catalog"] as const).map((t) => (
            <button
              key={t}
              className="rounded-md px-3 py-1 text-xs font-medium capitalize"
              style={tab === t ? { background: "var(--card)", boxShadow: "var(--shadow)" } : { color: "var(--muted)" }}
              onClick={() => setTab(t)}
            >
              {t} {t === "installed" ? `(${servers.length})` : `(${catalog.length})`}
            </button>
          ))}
        </div>

        {!system.node && (
          <div className="mb-3 flex items-start gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: "color-mix(in srgb, var(--warn) 10%, transparent)", color: "var(--warn)" }}>
            <AlertTriangle size={13} className="mt-0.5" />
            Node.js (`npx`) was not found on PATH. Most MCP servers need it. Install Node 20+ and restart the core.
          </div>
        )}
        {!system.uv && (
          <div className="mb-3 flex items-start gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: "var(--panel)", color: "var(--muted)" }}>
            <AlertTriangle size={13} className="mt-0.5" />
            `uvx` was not found. uv-based servers (Fetch, Time, Git, Alpaca) need `pip install uv`.
          </div>
        )}

        {tab === "installed" && (
          servers.length === 0 ? (
            <Empty icon={<Plug size={20} />} title="No MCP servers configured" body="Add Context7, Playwright, Firecrawl or a custom server from the catalog."
              action={<button className="btn btn-primary" onClick={() => setTab("catalog")}><Download size={14} /> Browse catalog</button>} />
          ) : (
            <div className="space-y-2.5">
              {servers.map((s) => (
                <div key={s.id} className="card p-4">
                  <div className="flex flex-wrap items-start gap-2">
                    <StatusDot status={s.status} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-semibold">{s.name}</h3>
                        <span className="chip">{s.category}</span>
                        <span className="chip">{s.transport}</span>
                        {s.status === "running" && <span className="chip chip-ok">{s.tool_count} tools</span>}
                        {s.auto_start && <span className="chip chip-accent">auto</span>}
                      </div>
                      <p className="mt-1 truncate font-mono text-[11px]" style={{ color: "var(--muted)" }}>
                        {s.transport === "stdio" ? `${s.command} ${s.args.join(" ")}` : s.url}
                      </p>
                      {s.notes && <p className="mt-0.5 text-[11px]" style={{ color: "var(--muted)" }}>{s.notes}</p>}
                      {s.error && (
                        <p className="mt-1 rounded px-2 py-1 font-mono text-[10px]" style={{ background: "color-mix(in srgb, var(--err) 8%, transparent)", color: "var(--err)" }}>
                          {s.error}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {s.status === "running" ? (
                        <button className="btn btn-sm" onClick={() => stop(s)} disabled={busy === s.id}>
                          {busy === s.id ? <Spinner /> : <Square size={11} />} Stop
                        </button>
                      ) : (
                        <button className="btn btn-primary btn-sm" onClick={() => start(s)} disabled={busy === s.id}>
                          {busy === s.id ? <Spinner /> : <Play size={11} />} Start
                        </button>
                      )}
                      <button className="btn btn-sm" onClick={() => test(s)} disabled={busy === s.id}>
                        <Zap size={11} /> Test
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={() => setEditing({ ...s, serverId: s.id })} title="Edit">
                        <Pencil size={12} />
                      </button>
                      <button className="btn btn-ghost btn-sm btn-danger" onClick={() => remove(s)} title="Remove">
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>

                  {s.status === "running" && (
                    <div className="mt-2">
                      <button className="flex items-center gap-1 text-[11px]" style={{ color: "var(--muted)" }} onClick={() => setExpanded(expanded === s.id ? "" : s.id)}>
                        {expanded === s.id ? <ChevronDown size={12} /> : <ChevronRight size={12} />} tools ({s.tools.length})
                      </button>
                      {expanded === s.id && (
                        <div className="mt-1.5 grid gap-1 sm:grid-cols-2">
                          {s.tools.map((t) => (
                            <button
                              key={t.name}
                              className="flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-[11px]"
                              style={{ background: "var(--panel)" }}
                              onClick={() => setCallTool({ server: s, tool: t })}
                              title="Call this tool"
                            >
                              <Terminal size={10} style={{ color: "var(--accent)" }} />
                              <span className="truncate font-mono">{t.name}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )
        )}

        {tab === "catalog" && (
          <div className="grid gap-3 md:grid-cols-2">
            {catalog.map((item) => (
              <div key={item.id} className="card p-4">
                <div className="flex items-start gap-2">
                  {item.category === "browser" ? <Globe size={15} style={{ color: "var(--accent)", marginTop: 2 }} /> : <Plug size={15} style={{ color: "var(--accent)", marginTop: 2 }} />}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <h3 className="text-sm font-semibold">{item.name}</h3>
                      <span className="chip">{item.category}</span>
                      {item.installed && <span className="chip chip-ok">added</span>}
                    </div>
                    <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--muted)" }}>{item.notes}</p>
                    <p className="mt-1 truncate font-mono text-[10px]" style={{ color: "var(--muted)" }}>
                      {item.transport === "stdio" ? `${item.command} ${(item.args || []).join(" ")}` : item.url}
                    </p>
                  </div>
                </div>
                <button className="btn btn-sm mt-3" onClick={() => addFromCatalog(item)} disabled={item.installed}>
                  {item.installed ? "Already added" : "Add server"}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {editing && (
        <McpForm
          draft={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await refresh();
          }}
        />
      )}

      {callTool && (
        <ToolCallModal
          server={callTool.server}
          tool={callTool.tool}
          onClose={() => setCallTool(null)}
        />
      )}
    </div>
  );
}

function McpForm({ draft, onClose, onSaved }: { draft: Draft; onClose: () => void; onSaved: () => Promise<void> }) {
  const { push } = useToast();
  const isEdit = Boolean(draft.serverId);
  const [name, setName] = useState(draft.name);
  const [transport, setTransport] = useState(draft.transport || "stdio");
  const [command, setCommand] = useState(draft.command);
  const [args, setArgs] = useState(JSON.stringify(draft.args || [], null, 2));
  const [url, setUrl] = useState(draft.url);
  const [env, setEnv] = useState(JSON.stringify(draft.env || {}, null, 2));
  const [category, setCategory] = useState(draft.category || "general");
  const [notes, setNotes] = useState(draft.notes);
  const [autoStart, setAutoStart] = useState(draft.auto_start);
  const [enabled, setEnabled] = useState(draft.enabled);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      let parsedArgs: string[] = [];
      let parsedEnv: Record<string, string> = {};
      try {
        parsedArgs = args.trim() ? JSON.parse(args) : [];
        parsedEnv = env.trim() ? JSON.parse(env) : {};
      } catch {
        throw new Error("Args and env must be valid JSON");
      }
      const payload = {
        name, transport, command, args: parsedArgs, url, env: parsedEnv,
        category, notes, auto_start: autoStart, enabled,
      };
      await (isEdit
        ? api.patch(`/api/mcp/${draft.serverId}`, payload)
        : api.post("/api/mcp", payload));
      push(isEdit ? "MCP server updated. Restart it to apply changes." : "MCP server added. Start it to discover tools.");
      await onSaved();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} wide title={isEdit ? "Edit MCP server" : "Add MCP server"} subtitle="stdio spawns a local process; http connects to a Streamable HTTP endpoint.">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <Field label="Transport">
          <select className="select" value={transport} onChange={(e) => setTransport(e.target.value)}>
            <option value="stdio">stdio (local process)</option>
            <option value="http">http (Streamable HTTP)</option>
          </select>
        </Field>
        {transport === "stdio" ? (
          <>
            <Field label="Command" hint="npx, uvx, node, python…">
              <input className="input font-mono text-xs" value={command} onChange={(e) => setCommand(e.target.value)} />
            </Field>
            <Field label="Args (JSON array)">
              <textarea className="textarea font-mono text-[11px]" rows={3} value={args} onChange={(e) => setArgs(e.target.value)} />
            </Field>
          </>
        ) : (
          <Field label="Endpoint URL" className="sm:col-span-2">
            <input className="input font-mono text-xs" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/mcp" />
          </Field>
        )}
        <Field label="Env / headers (JSON)" className="sm:col-span-2" hint="Secrets live in the local vault. Masked values are kept as-is; edit a value to replace it.">
          <textarea className="textarea font-mono text-[11px]" rows={4} value={env} onChange={(e) => setEnv(e.target.value)} />
        </Field>
        <Field label="Category"><input className="input" value={category} onChange={(e) => setCategory(e.target.value)} /></Field>
        <Field label="Notes"><input className="input" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        <div className="sm:col-span-2 flex flex-col gap-2">
          <Toggle checked={enabled} onChange={setEnabled} label="Enabled" />
          <Toggle checked={autoStart} onChange={setAutoStart} label="Start automatically with the core" hint="Only for servers you trust." />
        </div>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={saving || !name || (transport === "stdio" ? !command : !url)} onClick={save}>
          {saving && <Spinner />} {isEdit ? "Save" : "Add server"}
        </button>
      </div>
    </Modal>
  );
}

function ToolCallModal({ server, tool, onClose }: { server: McpServer; tool: McpTool; onClose: () => void }) {
  const { push } = useToast();
  const [args, setArgs] = useState("{}");
  const [result, setResult] = useState<unknown>(null);
  const [running, setRunning] = useState(false);

  async function run() {
    setRunning(true);
    try {
      const parsed = JSON.parse(args || "{}");
      const res = await api.post<{ ok: boolean; error?: string; result?: unknown; text?: string }>(
        `/api/mcp/${server.id}/call`,
        { tool: tool.name, arguments: parsed },
      );
      setResult(res);
      if (!res.ok) push(res.error || "Tool failed", "error");
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setRunning(false);
    }
  }

  return (
    <Modal open onClose={onClose} wide title={tool.name} subtitle={`${server.name} · ${tool.description || "no description"}`}>
      <Field label="Arguments (JSON)">
        <textarea className="textarea font-mono text-[11px]" rows={6} value={args} onChange={(e) => setArgs(e.target.value)} />
      </Field>
      <div className="mt-2">
        <button className="btn btn-primary btn-sm" onClick={run} disabled={running}>
          {running ? <Spinner /> : <Zap size={12} />} Run tool
        </button>
      </div>
      {result ? (
        <div className="mt-3">
          <div className="label">Result</div>
          <JsonBox value={result} />
        </div>
      ) : null}
      <div className="mt-3">
        <div className="label">Input schema</div>
        <JsonBox value={tool.input_schema} />
      </div>
    </Modal>
  );
}
