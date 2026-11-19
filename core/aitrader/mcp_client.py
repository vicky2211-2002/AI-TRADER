"""Minimal, dependency-free MCP (Model Context Protocol) client.

Implements the JSON-RPC 2.0 subset used by MCP:
  initialize -> notifications/initialized -> tools/list -> tools/call

Transports:
  * stdio  : newline-delimited JSON over a child process (npx / uvx / python)
  * http   : Streamable HTTP JSON-RPC endpoint (StreamableHTTPServerTransport)

Deliberately hand-rolled so AI-TRADER does not pin an MCP SDK version and
keeps working when the SDK changes. Errors are surfaced, never swallowed.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from typing import Any

import httpx

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "ai-trader", "version": "0.1.0"}


class MCPError(RuntimeError):
    pass


def _resolve_command(command: str) -> str:
    if not command:
        raise MCPError("No command configured for this MCP server.")
    found = shutil.which(command)
    if found:
        return found
    for suffix in (".cmd", ".exe", ".bat", ".ps1"):
        found = shutil.which(command + suffix)
        if found:
            return found
    raise MCPError(
        f"Command '{command}' was not found on PATH. Install Node.js (npx) or uv (uvx) and retry."
    )


def _expand_env(env: dict) -> dict:
    out = {}
    for key, value in (env or {}).items():
        out[str(key)] = os.path.expandvars(str(value))
    return out


def _clean_schema(schema: Any) -> dict:
    if isinstance(schema, dict):
        return schema
    return {"type": "object", "properties": {}}


class StdioMCPClient:
    def __init__(self, name: str, command: str, args: list[str], env: dict, cwd: str | None = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.cwd = cwd
        self.proc: subprocess.Popen | None = None
        self._id = 0
        self._pending: dict[int, queue.Queue] = {}
        self._lock = threading.RLock()
        self._reader: threading.Thread | None = None
        self._stderr: list[str] = []
        self.server_info: dict = {}
        self.tools: list[dict] = []

    # -- lifecycle ---------------------------------------------------------
    def start(self, timeout: float = 45.0) -> None:
        if self.proc and self.proc.poll() is None:
            return
        exe = _resolve_command(self.command)
        cmd = [exe, *[str(a) for a in self.args]]
        full_env = os.environ.copy()
        full_env.update(_expand_env(self.env))
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=full_env,
                cwd=self.cwd or None,
                creationflags=flags,
            )
        except FileNotFoundError as exc:
            raise MCPError(f"Could not launch '{self.command}': {exc}") from exc

        self._reader = threading.Thread(target=self._read_loop, name=f"mcp-{self.name}", daemon=True)
        self._reader.start()
        threading.Thread(target=self._stderr_loop, name=f"mcp-err-{self.name}", daemon=True).start()

        result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"roots": {"listChanged": False}, "sampling": {}},
                "clientInfo": CLIENT_INFO,
            },
            timeout=timeout,
        )
        self.server_info = result or {}
        self.notify("notifications/initialized", {})
        self.tools = self.list_tools(timeout=timeout)

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if not proc:
            return
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def alive(self) -> bool:
        return bool(self.proc and self.proc.poll() is None)

    # -- io ----------------------------------------------------------------
    def _read_loop(self) -> None:
        proc = self.proc
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg_id = msg.get("id")
            if msg_id is not None and msg_id in self._pending:
                self._pending[msg_id].put(msg)
        # wake anyone still waiting
        for q in list(self._pending.values()):
            q.put({"error": {"message": "MCP process exited"}})

    def _stderr_loop(self) -> None:
        proc = self.proc
        if not proc or not proc.stderr:
            return
        for line in proc.stderr:
            if line:
                self._stderr.append(line.rstrip())
                self._stderr[:] = self._stderr[-80:]

    def _write(self, payload: dict) -> None:
        if not self.proc or not self.proc.stdin:
            raise MCPError("MCP process is not running.")
        try:
            self.proc.stdin.write(json.dumps(payload) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPError(f"MCP process closed the pipe: {exc}") from exc

    def request(self, method: str, params: dict | None = None, timeout: float = 60.0) -> Any:
        with self._lock:
            self._id += 1
            req_id = self._id
            q: queue.Queue = queue.Queue()
            self._pending[req_id] = q
            self._write({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        try:
            msg = q.get(timeout=timeout)
        except queue.Empty:
            raise MCPError(f"Timed out waiting for '{method}' after {timeout:.0f}s.")
        finally:
            self._pending.pop(req_id, None)
        if "error" in msg:
            err = msg["error"]
            raise MCPError(str(err.get("message") if isinstance(err, dict) else err))
        return msg.get("result")

    def notify(self, method: str, params: dict | None = None) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def list_tools(self, timeout: float = 60.0) -> list[dict]:
        result = self.request("tools/list", {}, timeout=timeout) or {}
        tools = []
        for t in result.get("tools") or []:
            tools.append(
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "input_schema": _clean_schema(t.get("inputSchema")),
                }
            )
        return tools

    def call_tool(self, name: str, arguments: dict, timeout: float = 120.0) -> dict:
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout)
        return result or {}

    def stderr_tail(self, lines: int = 12) -> str:
        return "\n".join(self._stderr[-lines:])


class HttpMCPClient:
    """Streamable HTTP MCP client (single JSON-RPC endpoint)."""

    def __init__(self, name: str, url: str, headers: dict | None = None):
        self.name = name
        self.url = url
        self.headers = headers or {}
        self.session_id = ""
        self._id = 0
        self.server_info: dict = {}
        self.tools: list[dict] = []
        self._client = httpx.Client(timeout=60, follow_redirects=True)

    def _post(self, payload: dict, timeout: float = 60.0) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        resp = self._client.post(self.url, headers=headers, json=payload, timeout=timeout)
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if resp.status_code >= 400:
            raise MCPError(f"HTTP {resp.status_code}: {resp.text[:400]}")
        ctype = resp.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    body = line[5:].strip()
                    if not body:
                        continue
                    try:
                        msg = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                    if msg.get("id") == payload.get("id"):
                        return msg
            raise MCPError("SSE stream ended without a matching response id.")
        return resp.json()

    def start(self, timeout: float = 45.0) -> None:
        result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
            timeout=timeout,
        )
        self.server_info = result or {}
        try:
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        except Exception:
            pass
        self.tools = self.list_tools(timeout=timeout)

    def stop(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def alive(self) -> bool:
        return True

    def request(self, method: str, params: dict | None = None, timeout: float = 60.0) -> Any:
        self._id += 1
        msg = self._post(
            {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}},
            timeout=timeout,
        )
        if "error" in msg:
            err = msg["error"]
            raise MCPError(str(err.get("message") if isinstance(err, dict) else err))
        return msg.get("result")

    def notify(self, method: str, params: dict | None = None) -> None:
        try:
            self._post({"jsonrpc": "2.0", "method": method, "params": params or {}})
        except Exception:
            pass

    def list_tools(self, timeout: float = 60.0) -> list[dict]:
        result = self.request("tools/list", {}, timeout=timeout) or {}
        return [
            {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "input_schema": _clean_schema(t.get("inputSchema")),
            }
            for t in result.get("tools") or []
        ]

    def call_tool(self, name: str, arguments: dict, timeout: float = 120.0) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout) or {}

    def stderr_tail(self, lines: int = 12) -> str:
        return ""


def make_client(row: dict):
    transport = (row.get("transport") or "stdio").lower()
    if transport in ("http", "streamable-http", "sse"):
        url = row.get("url") or ""
        if transport == "sse" and url and not url.rstrip("/").endswith("/mcp"):
            url = url.rstrip("/") + "/mcp"
        headers = _expand_env(json.loads(row.get("env_json") or "{}"))
        return HttpMCPClient(row.get("name") or row.get("id"), url, headers)
    args = json.loads(row.get("args_json") or "[]")
    env = json.loads(row.get("env_json") or "{}")
    return StdioMCPClient(row.get("name") or row.get("id"), row.get("command") or "", args, env)


class MCPManager:
    """Owns live MCP connections for the local core process."""

    def __init__(self):
        self._clients: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._errors: dict[str, str] = {}

    def start(self, row: dict, timeout: float = 45.0) -> Any:
        server_id = row["id"]
        with self._lock:
            existing = self._clients.get(server_id)
            if existing and existing.alive():
                return existing
            client = make_client(row)
        self._clients[server_id] = client
        try:
            client.start(timeout=timeout)
            self._errors.pop(server_id, None)
        except Exception as exc:
            self._errors[server_id] = str(exc)
            raise
        return client

    def stop(self, server_id: str) -> None:
        with self._lock:
            client = self._clients.pop(server_id, None)
        if client:
            client.stop()
        self._errors.pop(server_id, None)

    def stop_all(self) -> None:
        for sid in list(self._clients):
            self.stop(sid)

    def get(self, server_id: str):
        return self._clients.get(server_id)

    def is_running(self, server_id: str) -> bool:
        client = self._clients.get(server_id)
        return bool(client and client.alive())

    def error(self, server_id: str) -> str:
        return self._errors.get(server_id, "")

    def tools(self, row: dict) -> list[dict]:
        client = self.start(row)
        return client.tools or []

    def call(self, row: dict, tool: str, args: dict, timeout: float = 120.0) -> dict:
        client = self.start(row)
        return client.call_tool(tool, args, timeout=timeout)


def content_to_text(result: dict) -> str:
    """Flatten an MCP tools/call result into readable text."""
    if not isinstance(result, dict):
        return str(result)
    parts: list[str] = []
    for item in result.get("content") or []:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        if item.get("type") == "text":
            parts.append(str(item.get("text", "")))
        elif item.get("type") == "resource":
            res = item.get("resource") or {}
            parts.append(str(res.get("text") or res.get("uri") or ""))
        elif item.get("type") == "image":
            parts.append("[image result]")
        else:
            parts.append(json.dumps(item)[:2000])
    if not parts and result.get("toolResult") is not None:
        parts.append(json.dumps(result["toolResult"])[:4000])
    return "\n".join(p for p in parts if p).strip()
