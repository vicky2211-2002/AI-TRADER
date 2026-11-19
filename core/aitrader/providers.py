"""Unified LLM provider client.

Supports the three protocols that cover virtually every vendor:
  * openai      -> OpenAI, Groq, Cerebras, NVIDIA NIM, OpenRouter, Ollama,
                   Together, Fireworks, DeepSeek, xAI, Mistral, vLLM, LM Studio
  * anthropic   -> Claude API
  * google      -> Gemini Generative Language API

Everything is plain httpx so no vendor SDK is required.
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

DEFAULT_TIMEOUT = 90.0


class ProviderError(RuntimeError):
    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body[:2000]


def _base(url: str) -> str:
    return (url or "").rstrip("/")


def _headers(kind: str, api_key: str, extra: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json", "User-Agent": "AI-TRADER/0.1"}
    if kind == "anthropic":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    elif kind == "google":
        headers["x-goog-api-key"] = api_key
    elif kind == "azure":
        headers["api-key"] = api_key
    elif api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if extra:
        headers.update({str(k): str(v) for k, v in extra.items() if k})
    return headers


def _error_message(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err)
            if isinstance(err, str):
                return err
            if data.get("message"):
                return str(data["message"])
    except Exception:
        pass
    return (resp.text or f"HTTP {resp.status_code}")[:500]


# ---------------------------------------------------------------------------
# Message conversion
# ---------------------------------------------------------------------------
def _openai_messages(messages: list[dict], system: str | None) -> list[dict]:
    out: list[dict] = []
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        role = m.get("role", "user")
        if role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": m.get("tool_call_id", ""),
                    "content": str(m.get("content", "")),
                }
            )
            continue
        if role == "assistant" and m.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    "content": m.get("content") or "",
                    "tool_calls": m["tool_calls"],
                }
            )
            continue
        out.append({"role": role, "content": m.get("content", "")})
    return out


def _anthropic_payload(messages: list[dict], system: str | None, tools: list[dict] | None):
    sys_parts = []
    converted: list[dict] = []
    if system:
        sys_parts.append({"type": "text", "text": system})
    for m in messages:
        role = m.get("role", "user")
        if role == "system":
            sys_parts.append({"type": "text", "text": str(m.get("content", ""))})
            continue
        if role == "tool":
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.get("tool_call_id", ""),
                            "content": str(m.get("content", "")),
                        }
                    ],
                }
            )
            continue
        if role == "assistant" and m.get("tool_calls"):
            blocks: list[dict] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for idx, tc in enumerate(m["tool_calls"]):
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id") or f"toolu_{idx}",
                        "name": fn.get("name", ""),
                        "input": args,
                    }
                )
            converted.append({"role": "assistant", "content": blocks})
            continue
        converted.append({"role": "assistant" if role == "assistant" else "user",
                          "content": [{"type": "text", "text": str(m.get("content", ""))}]})
    # Anthropic wants the first message to be a user message.
    if converted and converted[0]["role"] == "assistant":
        converted.insert(0, {"role": "user", "content": [{"type": "text", "text": "Continue."}]})
    payload: dict[str, Any] = {"messages": converted, "max_tokens": 1600}
    if sys_parts:
        payload["system"] = sys_parts
    if tools:
        payload["tools"] = [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get("parameters", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]
    return payload


def _google_payload(messages: list[dict], system: str | None, tools: list[dict] | None):
    contents = []
    for m in messages:
        role = m.get("role", "user")
        if role == "system":
            continue
        if role == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": m.get("tool_name", "tool"),
                                "response": {"result": str(m.get("content", ""))},
                            }
                        }
                    ],
                }
            )
            continue
        if role == "assistant" and m.get("tool_calls"):
            parts = []
            if m.get("content"):
                parts.append({"text": m["content"]})
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                parts.append({"functionCall": {"name": fn.get("name", ""), "args": args}})
            contents.append({"role": "model", "parts": parts})
            continue
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": str(m.get("content", ""))}],
            }
        )
    payload: dict[str, Any] = {"contents": contents}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        payload["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": t["function"]["name"],
                        "description": t["function"].get("description", ""),
                        "parameters": t["function"].get("parameters", {"type": "object", "properties": {}}),
                    }
                    for t in tools
                ]
            }
        ]
    return payload


# ---------------------------------------------------------------------------
# Normalised response: {"text", "tool_calls", "usage", "raw"}
# ---------------------------------------------------------------------------
def _normalise_openai(data: dict) -> dict:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        calls.append(
            {
                "id": tc.get("id") or "",
                "type": "function",
                "function": {"name": fn.get("name", ""), "arguments": fn.get("arguments") or "{}"},
            }
        )
    return {
        "text": msg.get("content") or "",
        "tool_calls": calls,
        "usage": data.get("usage") or {},
        "raw": data,
    }


def _normalise_anthropic(data: dict) -> dict:
    texts, calls = [], []
    for block in data.get("content") or []:
        if block.get("type") == "text":
            texts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            calls.append(
                {
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input") or {}),
                    },
                }
            )
    return {
        "text": "".join(texts).strip(),
        "tool_calls": calls,
        "usage": data.get("usage") or {},
        "raw": data,
    }


def _normalise_google(data: dict) -> dict:
    texts, calls = [], []
    candidates = data.get("candidates") or []
    for part in ((candidates[0].get("content") or {}).get("parts") if candidates else []) or []:
        if part.get("text"):
            texts.append(part["text"])
        if part.get("functionCall"):
            fc = part["functionCall"]
            calls.append(
                {
                    "id": fc.get("id") or f"call_{len(calls)}",
                    "type": "function",
                    "function": {
                        "name": fc.get("name", ""),
                        "arguments": json.dumps(fc.get("args") or {}),
                    },
                }
            )
    return {
        "text": "".join(texts).strip(),
        "tool_calls": calls,
        "usage": data.get("usageMetadata") or {},
        "raw": data,
    }


async def chat(
    *,
    kind: str,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    system: str | None = None,
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    max_tokens: int = 1200,
    extra_headers: dict | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    kind = (kind or "openai").lower()
    base = _base(base_url)
    headers = _headers(kind, api_key, extra_headers)

    if kind == "anthropic":
        url = f"{base}/messages" if not base.endswith("/messages") else base
        payload = _anthropic_payload(messages, system, tools)
        payload["model"] = model
        payload["temperature"] = temperature
        payload["max_tokens"] = max_tokens
        normalise = _normalise_anthropic
    elif kind == "google":
        url = f"{base}/models/{model}:generateContent"
        payload = _google_payload(messages, system, tools)
        payload["generationConfig"] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        normalise = _normalise_google
    elif kind == "azure":
        url = f"{base}/openai/deployments/{model}/chat/completions?api-version=2024-10-21"
        payload = {
            "messages": _openai_messages(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        normalise = _normalise_openai
    else:
        url = f"{base}/chat/completions" if not base.endswith("/chat/completions") else base
        payload = {
            "model": model,
            "messages": _openai_messages(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        normalise = _normalise_openai

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise ProviderError(f"Timeout after {timeout:.0f}s") from exc
    except httpx.HTTPError as exc:
        raise ProviderError(f"Network error: {exc}") from exc

    if resp.status_code >= 400:
        raise ProviderError(_error_message(resp), resp.status_code, resp.text)
    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise ProviderError("Provider returned non-JSON response", resp.status_code, resp.text) from exc
    out = normalise(data)
    out["model"] = model
    return out


async def test_provider(row: dict, api_key: str) -> dict:
    started = time.perf_counter()
    try:
        result = await chat(
            kind=row.get("kind", "openai"),
            base_url=row.get("base_url", ""),
            api_key=api_key,
            model=row.get("model", ""),
            messages=[{"role": "user", "content": "Reply with the single word: OK"}],
            temperature=0,
            max_tokens=64,
            extra_headers=json.loads(row.get("headers_json") or "{}"),
            timeout=45,
        )
        latency = int((time.perf_counter() - started) * 1000)
        return {
            "ok": True,
            "latency_ms": latency,
            "reply": (result.get("text") or "").strip()[:300] or "(empty reply)",
            "model": row.get("model"),
            "usage": result.get("usage") or {},
        }
    except ProviderError as exc:
        return {
            "ok": False,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": str(exc),
            "status": exc.status,
            "hint": _hint(exc.status),
        }
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "latency_ms": 0, "error": str(exc)[:400], "hint": ""}


def _hint(status: int) -> str:
    return {
        401: "Wrong or missing API key.",
        403: "Key valid but the model/account is not allowed.",
        404: "Wrong base URL or model id.",
        429: "Rate limited - switch provider or wait.",
        500: "Provider error - retry or switch.",
        502: "Provider gateway error - retry.",
        503: "Provider overloaded - switch provider.",
    }.get(status, "")


async def list_models(row: dict, api_key: str) -> list[str]:
    kind = (row.get("kind") or "openai").lower()
    base = _base(row.get("base_url", ""))
    headers = _headers(kind, api_key, json.loads(row.get("headers_json") or "{}"))
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            if kind == "google":
                resp = await client.get(f"{base}/models", headers=headers)
                data = resp.json()
                return [
                    m.get("name", "").replace("models/", "")
                    for m in data.get("models") or []
                    if m.get("name")
                ]
            if kind == "anthropic":
                resp = await client.get(f"{base}/models", headers=headers)
                data = resp.json()
                return [m.get("id") for m in data.get("data") or [] if m.get("id")]
            resp = await client.get(f"{base}/models", headers=headers)
            data = resp.json()
            items = data.get("data") if isinstance(data, dict) else data
            out = []
            for m in items or []:
                if isinstance(m, str):
                    out.append(m)
                elif isinstance(m, dict) and m.get("id"):
                    out.append(m["id"])
            return sorted(set(out))[:400]
    except Exception:
        return []
