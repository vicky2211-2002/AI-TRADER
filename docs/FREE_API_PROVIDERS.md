# Free & low-cost AI providers

AI-TRADER talks to four wire formats:

- **OpenAI-compatible** — `POST /chat/completions` with `tools`, streaming SSE.
  This covers most vendors, routers and local servers.
- **Anthropic** — `POST /v1/messages`.
- **Google Gemini native** — `POST /v1beta/models/{model}:generateContent`.
- **Azure OpenAI** — OpenAI shape with a deployment name and `api-version`.

You do not need to edit code to add a vendor. **Models → Add provider**, pick the
kind, paste the base URL, model id and key, then press **Test**.

> Free tiers change without notice. Model ids below are the **seeded defaults**
> shipped in `core/seed/providers.json`; press **Refresh models** in the UI (or
> `GET /api/providers/{id}/models`) to see what your key can actually reach today.

---

## Seeded free providers

| Provider | Kind | Base URL | Seeded model | Key | Notes |
|----------|------|----------|--------------|-----|-------|
| **Google AI Studio (Gemini)** | openai | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-3.8-flash` | yes | Free tier, no card. OpenAI-compatible shim. |
| **Groq** | openai | `https://api.groq.com/openai/v1` | `qwen/qwen3.8-27b` | yes | Very low latency; good default for tool loops. |
| **Cerebras** | openai | `https://api.cerebras.ai/v1` | `gpt-oss-120b` | yes | Extremely high tokens/sec, shared queue. |
| **NVIDIA NIM** | openai | `https://integrate.api.nvidia.com/v1` | `mistralai/mistral-large-4-1t-a52b` | yes | Free developer credits; queue can be slow. |
| **OpenRouter** | openai | `https://openrouter.ai/api/v1` | `openrouter/free` | yes | Routes to whatever free model is live. Free ids end in `:free`. |
| **Ollama (local)** | openai | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` | no | Offline. `ollama serve` first. |

OpenRouter sends two optional attribution headers by default:
`HTTP-Referer: http://localhost` and `X-Title: AI-TRADER`. Edit them in the
provider form if you publish an app.

### Getting each key

| Provider | Where | Typical free allowance |
|----------|-------|------------------------|
| Google AI Studio | <https://aistudio.google.com/apikey> | Per-minute/per-day request caps on Flash models |
| Groq | <https://console.groq.com/keys> | Requests/min + tokens/min per model |
| Cerebras | <https://cloud.cerebras.ai> | Shared free inference queue |
| NVIDIA NIM | <https://build.nvidia.com> | Developer credits, expires |
| OpenRouter | <https://openrouter.ai/keys> | Free models with per-minute limits |
| Ollama | local install | Your GPU/CPU |

---

## Other good free or cheap options

Add these the same way: **Add provider → OpenAI-compatible**.

| Provider | Base URL | Example model | Why use it |
|----------|----------|---------------|------------|
| **Mistral** | `https://api.mistral.ai/v1` | `mistral-small-latest` | Free experiment tier; good EU data posture |
| **GitHub Models** | `https://models.inference.ai.azure.com` | `gpt-4o-mini` | Free with a GitHub token, low limits |
| **Together AI** | `https://api.together.xyz/v1` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` | Free starter credit, many open models |
| **Fireworks** | `https://api.fireworks.ai/inference/v1` | `accounts/fireworks/models/llama-v3p3-70b-instruct` | Fast open-model hosting |
| **DeepInfra** | `https://api.deepinfra.com/v1/openai` | `meta-llama/Llama-3.3-70B-Instruct` | Cheap per-token |
| **Hyperbolic** | `https://api.hyperbolic.xyz/v1` | `meta-llama/Llama-3.3-70B-Instruct` | Cheap open models |
| **Cloudflare Workers AI** | `https://api.cloudflare.com/client/v4/accounts/<account>/ai/v1` | `@cf/meta/llama-3.1-8b-instruct` | Free daily neurons |
| **DeepSeek** | `https://api.deepseek.com/v1` | `deepseek-chat` | Very cheap, strong reasoning |
| **Moonshot (Kimi)** | `https://api.moonshot.ai/v1` | `kimi-k2` | Long context |
| **Zhipu / GLM** | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` | Free Flash tier in some regions |
| **Alibaba DashScope** | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | `qwen-plus` | Free quota for new accounts |
| **xAI** | `https://api.x.ai/v1` | `grok-2-latest` | Credits on some plans |
| **Infron** | `https://llm.onerouter.pro/v1` | `z-ai/glm-5.1:free` | Free GLM routing (see the project’s Infron skill) |
| **ZenMux** | `https://zenmux.ai/api/v1` | `claude-sonnet-5-free` | Free Claude tier while available |

> Router endpoints (`openrouter/free`, `llm.onerouter.pro`, `zenmux.ai`) can
> change models hourly. If a chat fails with 404/model-not-found, open **Models**,
> press **Refresh models**, and pick a live id.

---

## Local / self-hosted

| Server | Base URL | Notes |
|--------|----------|-------|
| **Ollama** | `http://127.0.0.1:11434/v1` | Easiest. `ollama pull qwen2.5:7b` |
| **LM Studio** | `http://127.0.0.1:1234/v1` | Enable the local server in the app |
| **vLLM** | `http://127.0.0.1:8000/v1` | `vllm serve <model>`; needs a GPU |
| **llama.cpp server** | `http://127.0.0.1:8080/v1` | `llama-server -m model.gguf` |
| **text-generation-webui** | `http://127.0.0.1:5000/v1` | Enable the OpenAI extension |

Local models are the only ones that work fully offline and cost nothing per
token. For tool calling, prefer models with a native tools template (Qwen 2.5/3,
Llama 3.1+, Mistral Small 3+). A 7B model can run the analysis loop but will
mis-handle complex multi-tool plans; use 14B+ if you have the VRAM.

---

## Provider fields in the UI

| Field | Meaning |
|-------|---------|
| **Name** | Label in the model picker |
| **Kind** | `openai`, `anthropic`, `google`, `azure` |
| **Base URL** | Root, without `/chat/completions`. Trailing `/` is stripped. |
| **Model** | Default model id for new chats |
| **Models** | Comma-separated list shown in the picker; refreshed from `/models` when supported |
| **Headers** | Extra JSON headers (OpenRouter attribution, gateway keys) |
| **API key** | Stored encrypted; only a mask is ever returned |
| **Enabled** | Disabled providers disappear from the chat picker |
| **Default** | Preselected in a new chat |

### Test semantics

`POST /api/providers/{id}/test` sends a tiny prompt (`"Reply with OK"`), measures
latency, and records `last_status`, `last_latency_ms`, `last_checked`. It never
prints the key. A failure returns a short hint: 401 → wrong key, 404 → wrong base
URL or model, 429 → quota, timeout → network/proxy.

---

## Anthropic

| Field | Value |
|-------|-------|
| Kind | `anthropic` |
| Base URL | `https://api.anthropic.com` |
| Model | `claude-sonnet-4-5` (or whatever your account exposes) |
| Headers | leave empty; the client sends `anthropic-version: 2023-06-01` |

The client translates OpenAI-style `tools` into Anthropic `tools` and back, so
the agent loop is vendor-neutral. Anthropic has no permanent free tier; use it
for judgement-heavy analysis, not for every chat turn.

## Google Gemini (native)

Use native only if you need Gemini-specific features. For ordinary chat, the
seeded **OpenAI-compatible** Google endpoint is simpler and supports tools.

## Azure OpenAI

| Field | Value |
|-------|-------|
| Kind | `azure` |
| Base URL | `https://<resource>.openai.azure.com` |
| Model | your **deployment name** |
| Key | `api-key` |

The client appends `/openai/deployments/<model>/chat/completions?api-version=2024-10-21`.

---

## Choosing a model for trading work

| Job | Good fit | Avoid |
|-----|----------|-------|
| Fast quote/level commentary | Groq Qwen, Cerebras GPT-OSS, Gemini Flash | 70B models on CPU |
| Multi-tool planning (quote → candles → risk → order) | Gemini Flash, Claude Sonnet, GPT-class | 3B local models |
| News summarisation | Any 8B+ model | Models with tiny context |
| Offline / privacy | Ollama Qwen 2.5 7B–14B | Cloud-only vendors |
| Cheap bulk backtests commentary | DeepSeek, Gemini Flash-Lite | Premium reasoning tiers |

Practical default: **Groq or Gemini Flash for the chat loop**, **a stronger model
for the final trade rationale**. You can switch providers per conversation.

---

## Cost and rate-limit hygiene

1. **One test call, not a loop.** Do not poll `/models` every few seconds.
2. **Cache market data.** Quotes have a TTL; reuse them inside one turn.
3. **Cap tool iterations.** A model that keeps calling tools burns quota; the
   agent loop is bounded, but a bad prompt can still be expensive.
4. **Watch 429s.** The provider test records the failure; the chat surfaces it.
   Back off instead of retrying immediately.
5. **Never put a key in a prompt, skill or MCP env you do not trust.** MCP servers
   inherit their own env, not your provider keys.
6. **Rotate keys** if you ever pasted one into a chat or a public repo.

---

## Adding a provider by API

```bash
curl -X POST http://127.0.0.1:8765/api/providers \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Groq",
    "kind": "openai",
    "base_url": "https://api.groq.com/openai/v1",
    "model": "qwen/qwen3.8-27b",
    "models": ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"],
    "api_key": "gsk_...",
    "enabled": true,
    "is_default": true
  }'
```

Then `POST /api/providers/<id>/test`. The key is encrypted before it touches
SQLite and is never returned — only `key_hint` (last four characters).

---

## Related docs

- [MCP_CATALOG.md](MCP_CATALOG.md) — tools you can attach to any model
- [SECURITY_AND_RISK.md](SECURITY_AND_RISK.md) — where keys live and what they protect
- [API_REFERENCE.md](API_REFERENCE.md) — provider endpoints
