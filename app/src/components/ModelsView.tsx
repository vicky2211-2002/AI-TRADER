import { useState } from "react";
import { Cpu, Plus, RefreshCw, Trash2, Pencil, Star, Zap, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import type { Provider, SystemInfo } from "../lib/types";
import { api } from "../lib/api";
import { Empty, Field, Modal, Spinner, StatusDot, Toggle, useToast } from "./ui";

const KINDS = [
  { value: "openai", label: "OpenAI-compatible (most vendors)" },
  { value: "anthropic", label: "Anthropic (Claude)" },
  { value: "google", label: "Google Gemini (native)" },
  { value: "azure", label: "Azure OpenAI" },
];

export function ModelsView({
  providers,
  refresh,
  system,
}: {
  providers: Provider[];
  refresh: () => Promise<void>;
  system: SystemInfo;
}) {
  const { push } = useToast();
  const [editing, setEditing] = useState<Provider | "new" | null>(null);
  const [testing, setTesting] = useState<string>("");
  const [results, setResults] = useState<Record<string, { ok: boolean; latency_ms?: number; reply?: string; error?: string; hint?: string }>>({});

  async function test(p: Provider) {
    setTesting(p.id);
    try {
      const result = await api.post<{ ok: boolean; latency_ms?: number; reply?: string; error?: string; hint?: string }>(
        `/api/providers/${p.id}/test`,
      );
      setResults((prev) => ({ ...prev, [p.id]: result }));
      push(result.ok ? `${p.name}: ${result.latency_ms} ms` : `${p.name}: ${result.error}`, result.ok ? "ok" : "error");
      await refresh();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setTesting("");
    }
  }

  async function refreshModels(p: Provider) {
    try {
      const result = await api.get<{ models: string[] }>(`/api/providers/${p.id}/models`);
      push(result.models.length ? `${result.models.length} models found` : "No models returned (check key/base URL)", result.models.length ? "ok" : "info");
      await refresh();
    } catch (err) {
      push((err as Error).message, "error");
    }
  }

  async function setDefault(p: Provider) {
    await api.patch(`/api/providers/${p.id}`, { is_default: true });
    await refresh();
    push(`${p.name} is now the default model.`);
  }

  async function remove(p: Provider) {
    if (!confirm(`Delete provider "${p.name}"? The key is removed from the local vault.`)) return;
    await api.del(`/api/providers/${p.id}`);
    await refresh();
    push("Provider deleted.", "info");
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-5 py-6 md:px-8">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-display text-2xl">Models</h1>
            <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
              Bring any API. Keys stay in the local vault — never in the repo, never in chat.
            </p>
          </div>
          <button className="btn btn-primary" onClick={() => setEditing("new")}>
            <Plus size={15} /> Add provider
          </button>
        </div>

        {!system.vault.startsWith("fernet") && (
          <div className="mb-4 flex items-start gap-2 rounded-lg px-3 py-2 text-xs" style={{ background: "color-mix(in srgb, var(--warn) 10%, transparent)", color: "var(--warn)" }}>
            <AlertTriangle size={13} className="mt-0.5" />
            <span>
              `cryptography` is not installed, so the local vault is obfuscated rather than encrypted.
              Run `pip install cryptography` on the core machine for real encryption.
            </span>
          </div>
        )}

        {providers.length === 0 ? (
          <Empty
            icon={<Cpu size={20} />}
            title="No providers yet"
            body="Add a free OpenAI-compatible endpoint (Google AI Studio, Groq, Cerebras, OpenRouter) or local Ollama."
            action={<button className="btn btn-primary" onClick={() => setEditing("new")}><Plus size={14} /> Add provider</button>}
          />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {providers.map((p) => {
              const result = results[p.id];
              return (
                <div key={p.id} className="card p-4">
                  <div className="flex items-start gap-2">
                    <StatusDot status={p.last_status === "ok" ? "ok" : p.last_status === "error" ? "error" : "idle"} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate text-sm font-semibold">{p.name}</h3>
                        {p.is_default && <span className="chip chip-accent"><Star size={9} /> default</span>}
                        <span className="chip">{p.kind}</span>
                        {!p.has_key && !p.base_url.includes("localhost") && !p.base_url.includes("127.0.0.1") && (
                          <span className="chip chip-warn">no key</span>
                        )}
                      </div>
                      <p className="mt-1 truncate font-mono text-[11px]" style={{ color: "var(--muted)" }}>{p.model}</p>
                      <p className="mt-0.5 truncate font-mono text-[10px]" style={{ color: "var(--muted)" }}>{p.base_url}</p>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-1.5 text-[11px]" style={{ color: "var(--muted)" }}>
                    {p.key_hint && <span className="chip">key {p.key_hint}</span>}
                    {p.last_latency_ms > 0 && <span className="chip">{p.last_latency_ms} ms</span>}
                    {p.models.length > 0 && <span className="chip">{p.models.length} known</span>}
                    <span className="chip">{p.enabled ? "enabled" : "disabled"}</span>
                  </div>

                  {result && (
                    <div
                      className="mt-2 flex items-start gap-1.5 rounded-lg px-2 py-1.5 text-[11px]"
                      style={{
                        background: result.ok ? "color-mix(in srgb, var(--ok) 9%, transparent)" : "color-mix(in srgb, var(--err) 9%, transparent)",
                        color: result.ok ? "var(--ok)" : "var(--err)",
                      }}
                    >
                      {result.ok ? <CheckCircle2 size={12} className="mt-0.5" /> : <XCircle size={12} className="mt-0.5" />}
                      <span>
                        {result.ok ? `Connected in ${result.latency_ms} ms — "${result.reply}"` : result.error}
                        {!result.ok && result.hint ? ` (${result.hint})` : ""}
                      </span>
                    </div>
                  )}

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <button className="btn btn-sm" onClick={() => test(p)} disabled={testing === p.id}>
                      {testing === p.id ? <Spinner /> : <Zap size={12} />} Test
                    </button>
                    <button className="btn btn-sm" onClick={() => refreshModels(p)} title="Fetch /models">
                      <RefreshCw size={12} /> Models
                    </button>
                    {!p.is_default && (
                      <button className="btn btn-sm" onClick={() => setDefault(p)} title="Make default">
                        <Star size={12} /> Default
                      </button>
                    )}
                    <button className="btn btn-sm" onClick={() => setEditing(p)}>
                      <Pencil size={12} /> Edit
                    </button>
                    <button className="btn btn-sm btn-danger ml-auto" onClick={() => remove(p)}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="mt-6 rounded-xl p-4 text-xs leading-relaxed" style={{ background: "var(--panel)", color: "var(--muted)" }}>
          <strong style={{ color: "var(--text)" }}>Free starters:</strong> Google AI Studio
          (`https://generativelanguage.googleapis.com/v1beta/openai/`), Groq (`https://api.groq.com/openai/v1`),
          Cerebras (`https://api.cerebras.ai/v1`), OpenRouter (`https://openrouter.ai/api/v1`), and Ollama
          (`http://127.0.0.1:11434/v1`, no key). Full list in <span className="font-mono">docs/FREE_API_PROVIDERS.md</span>.
        </div>
      </div>

      {editing && (
        <ProviderForm
          provider={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await refresh();
          }}
        />
      )}
    </div>
  );
}

function ProviderForm({
  provider,
  onClose,
  onSaved,
}: {
  provider: Provider | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const { push } = useToast();
  const [name, setName] = useState(provider?.name || "");
  const [kind, setKind] = useState(provider?.kind || "openai");
  const [baseUrl, setBaseUrl] = useState(provider?.base_url || "https://api.groq.com/openai/v1");
  const [model, setModel] = useState(provider?.model || "");
  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState((provider?.models || []).join(", "));
  const [headers, setHeaders] = useState(JSON.stringify(provider?.headers || {}, null, 2));
  const [isDefault, setIsDefault] = useState(provider?.is_default || false);
  const [enabled, setEnabled] = useState(provider?.enabled ?? true);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      let parsedHeaders: Record<string, string> = {};
      try {
        parsedHeaders = headers.trim() ? JSON.parse(headers) : {};
      } catch {
        throw new Error("Headers must be valid JSON");
      }
      const payload: Record<string, unknown> = {
        name,
        kind,
        base_url: baseUrl,
        model,
        models: models.split(",").map((s) => s.trim()).filter(Boolean),
        headers: parsedHeaders,
        enabled,
        is_default: isDefault,
      };
      if (apiKey) payload.api_key = apiKey;
      if (provider) {
        await api.patch(`/api/providers/${provider.id}`, payload);
        push("Provider updated.");
      } else {
        await api.post("/api/providers", payload);
        push("Provider added. Click Test to verify it.");
      }
      await onSaved();
    } catch (err) {
      push((err as Error).message, "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title={provider ? "Edit provider" : "Add provider"}
      subtitle="OpenAI-compatible covers Groq, Cerebras, NVIDIA, OpenRouter, Ollama, DeepSeek, xAI and more."
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Display name">
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Groq (fast free)" />
        </Field>
        <Field label="Protocol">
          <select className="select" value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
          </select>
        </Field>
        <Field label="Base URL" className="sm:col-span-2">
          <input className="input font-mono text-xs" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.groq.com/openai/v1" />
        </Field>
        <Field label="Model id">
          <input className="input font-mono text-xs" value={model} onChange={(e) => setModel(e.target.value)} placeholder="qwen/qwen3.8-27b" />
        </Field>
        <Field label={provider?.has_key ? "API key (leave blank to keep)" : "API key"} hint={provider?.key_hint ? `Stored: ${provider.key_hint}` : "Stored encrypted on this machine."}>
          <input className="input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={provider?.has_key ? "••••••••" : "sk-..."} />
        </Field>
        <Field label="Known models (comma separated)" className="sm:col-span-2">
          <input className="input font-mono text-[11px]" value={models} onChange={(e) => setModels(e.target.value)} placeholder="model-a, model-b" />
        </Field>
        <Field label="Extra headers (JSON)" className="sm:col-span-2" hint="Optional, e.g. OpenRouter HTTP-Referer.">
          <textarea className="textarea font-mono text-[11px]" rows={3} value={headers} onChange={(e) => setHeaders(e.target.value)} />
        </Field>
        <div className="sm:col-span-2 flex flex-col gap-2 pt-1">
          <Toggle checked={enabled} onChange={setEnabled} label="Enabled" hint="Disabled providers are hidden from the chat picker." />
          <Toggle checked={isDefault} onChange={setIsDefault} label="Default model" hint="Used for new chats." />
        </div>
      </div>
      <div className="mt-5 flex justify-end gap-2">
        <button className="btn" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={saving || !name || !baseUrl || !model} onClick={save}>
          {saving ? <Spinner /> : null} {provider ? "Save changes" : "Add provider"}
        </button>
      </div>
    </Modal>
  );
}
