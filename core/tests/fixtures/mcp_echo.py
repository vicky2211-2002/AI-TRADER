"""Tiny MCP stdio server used by the offline test-suite."""
from __future__ import annotations

import json
import sys

TOOLS = [
    {
        "name": "echo",
        "description": "Echo text back",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    }
]


def reply(msg_id, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "initialize":
            reply(msg_id, {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-test", "version": "0.0.1"},
            })
        elif method == "tools/list":
            reply(msg_id, {"tools": TOOLS})
        elif method == "tools/call":
            args = (msg.get("params") or {}).get("arguments") or {}
            reply(msg_id, {"content": [{"type": "text", "text": str(args.get("text", ""))}]})
        elif method and msg_id is not None:
            reply(msg_id, error={"code": -32601, "message": f"unknown method {method}"})
        # notifications have no id and need no response


if __name__ == "__main__":
    main()
