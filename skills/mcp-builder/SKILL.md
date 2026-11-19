---
name: MCP Builder
description: Add, edit, test and remove MCP servers safely. Includes a checklist for unknown servers.
---

# MCP Builder

Use when the user wants a new MCP server, or an existing one fails to start.

## Anatomy of a server entry

```json
{
  "name": "Context7",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@upstash/context7-mcp"],
  "env": {"API_KEY": "..."},
  "category": "docs",
  "enabled": true,
  "auto_start": false
}
```

- `stdio`: the core spawns `command args` and speaks JSON-RPC over stdin/stdout.
- `http`: a Streamable HTTP endpoint (`https://host/mcp`).
- `env`: secrets are stored in the local vault, masked in the UI.

## Add procedure

1. Find the server's official package (npm or PyPI) and its exact run command.
2. Add it in MCP > Add server (or one-click from Catalog).
3. Start it. The UI shows the tool list and any stderr.
4. If it fails: check Node (`npx -v`) or uv (`uvx --version`) is installed, and
   that the command works in a terminal.
5. Call one read-only tool from the tools panel before letting the agent use it.
6. Enable `auto_start` only for servers you trust.

## Safety checklist for a new server

- [ ] Source is the official repo or a known vendor
- [ ] You know every tool it exposes
- [ ] Credentials are scoped (read-only where possible)
- [ ] No wallet keys, seed phrases, or broker passwords in `env`
- [ ] Filesystem server points at a dedicated folder, not `C:\`
- [ ] Write/delete/trade tools require approval (the core gates them by name)

## Troubleshooting

| Error | Cause |
|---|---|
| `command not found` | Node/uv missing, or npx not on PATH |
| `Timed out waiting for initialize` | package prompt/telemetry hanging; run it once manually |
| `HTTP 406` | endpoint is SSE, not Streamable HTTP; use `mcp-remote` |
| Tools list empty | server started but exposes no tools; check `server_info` |
| Process exits instantly | wrong package name or missing env var |

## Removing

Delete stops the process and removes the row. Bundled skills are unaffected.
