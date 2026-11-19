---
name: Model Provider Setup
description: Add and verify any OpenAI/Anthropic/Google-compatible endpoint, including free tiers.
---

# Model Provider Setup

Use when chat fails with 401/404/429, or the user wants to connect a new model.

## What you need

1. **Protocol**: `openai` (most vendors), `anthropic`, `google`, or `azure`.
2. **Base URL** - include `/v1` for OpenAI-compatible APIs.
3. **Model id** - exactly as the vendor writes it.
4. **Key** - stored encrypted in the local vault, never in the repo.

## Test matrix

| Symptom | Meaning | Fix |
|---|---|---|
| 401 | bad/missing key | paste the key again |
| 403 | key not allowed for that model | pick another model or plan |
| 404 | wrong base URL or model id | check `/models` list |
| 429 | rate limit | wait, or switch provider |
| timeout | free queue busy | retry, or switch to Groq/Cerebras |
| empty reply | reasoning model used all tokens | raise max tokens |

## Procedure

1. Add the provider in Models (name, protocol, base URL, model, key).
2. Click **Test**. A green result shows latency and a short reply.
3. Click **Refresh models** to pull the vendor's list.
4. Set as default if it is the daily driver.
5. In chat, the model picker switches instantly - keep a backup provider.

## Free-tier notes

- Free tiers change without notice. Re-test before relying on one.
- Google AI Studio, Groq, Cerebras and OpenRouter have usable free tiers.
- Ollama runs fully offline with no key (`http://127.0.0.1:11434/v1`).
- Never put a paid key in a screenshot or in the journal.

## Agent compatibility

Tool calling is required for the agent to read quotes and propose orders.
If a model ignores tools, use it for analysis only and keep a tool-capable model
as the default.
