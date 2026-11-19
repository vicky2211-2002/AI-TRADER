# MCP catalog

AI-TRADER speaks the [Model Context Protocol](https://modelcontextprotocol.io)
over two transports:

- **stdio** — the core spawns a local process (`npx`, `uvx`, a binary) and talks
  JSON-RPC over stdin/stdout.
- **Streamable HTTP** — the core POSTs JSON-RPC to a URL and accepts JSON or SSE.

There is no MCP SDK dependency. The client is a small, explicit JSON-RPC
implementation in `core/aitrader/mcp_client.py`, so a server that follows the spec
works regardless of SDK version bumps.

**MCP servers → Catalog** lists 22 vetted presets. **Install** copies one into
your server list; **Start** performs the handshake and caches its tools; **Test**
round-trips a call; the tool browser lets you invoke any tool manually.

---

## Prerequisites

| Need | Why | Check |
|------|-----|-------|
| Node.js 18+ / npm | `npx`-based servers | `npx --version` |
| `uv` / `uvx` | Python-based servers (`mcp-server-*`) | `uvx --version` |
| Docker | Servers you choose to run in a container | `docker --version` |

Settings → System shows whether `npx` and `uvx` were detected. A server whose
runtime is missing starts with `spawn npx ENOENT` or `uvx not found`.

---

## Seeded servers (pre-installed, disabled)

| Server | Transport | Command | Category | Enable when |
|--------|-----------|---------|----------|-------------|
| **Context7** | stdio | `npx -y @upstash/context7-mcp` | docs | You want current library/API docs |
| **Playwright** | stdio | `npx -y @playwright/mcp@latest` | browser | You need real browser automation/scraping |
| **Firecrawl** | stdio | `npx -y firecrawl-mcp` | browser | You have a Firecrawl key and want crawl/map |
| **Fetch** | stdio | `uvx mcp-server-fetch` | browser | You want URL → Markdown with a Python runtime |

They ship disabled on purpose: every extra server is extra attack surface and
extra startup time.

---

## Full catalog

### Browser & scraping

| Server | Install | Needs | What it gives the agent |
|--------|---------|-------|--------------------------|
| **Playwright** | `npx -y @playwright/mcp@latest` | Chromium (auto-installed) | Navigate, click, type, screenshot, extract text, handle JS-heavy sites |
| **Puppeteer** | `npx -y @modelcontextprotocol/server-puppeteer` | Chrome | Alternate browser stack; screenshots and DOM access |
| **Chrome DevTools** | `npx -y chrome-devtools-mcp@latest` | Chrome running | Console, network and performance inspection of a live page |
| **Firecrawl** | `npx -y firecrawl-mcp` | `FIRECRAWL_API_KEY` | Search, scrape, crawl, site map; clean Markdown output |
| **Fetch** | `uvx mcp-server-fetch` | `uv` | Single-page fetch → Markdown; respects robots.txt by default |

Use browser servers for broker portals, economic-calendar pages and news sites
that block plain HTTP. Keep them read-only unless you deliberately automate a
login.

### Search & research

| Server | Install | Needs | Notes |
|--------|---------|-------|-------|
| **Tavily** | `npx -y tavily-mcp` | `TAVILY_API_KEY` | Agent-optimised search with extracted answers |
| **Brave Search** | `npx -y @modelcontextprotocol/server-brave-search` | `BRAVE_API_KEY` | Independent index; good for news diversity |
| **Context7** | `npx -y @upstash/context7-mcp` | none | Version-accurate docs for libraries and APIs |
| **Everything** | `npx -y @modelcontextprotocol/server-everything` | none | Reference server; ideal for testing the transport |

### Files, memory, reasoning

| Server | Install | Needs | Notes |
|--------|---------|-------|-------|
| **Filesystem** | `npx -y @modelcontextprotocol/server-filesystem "${HOME}/Documents"` | none | Path-scoped read/write. Never point it at your home root. |
| **Memory** | `npx -y @modelcontextprotocol/server-memory` | none | Knowledge graph persisted across chats |
| **Sequential Thinking** | `npx -y @modelcontextprotocol/server-sequential-thinking` | none | Structured scratchpad for multi-step plans |
| **Time** | `uvx mcp-server-time` | `uv` | Timezone conversion, session clocks |
| **Git** | `uvx mcp-server-git --repository .` | `uv`, a repo | Local history and diffs |

### Developer tools

| Server | Install | Needs | Notes |
|--------|---------|-------|-------|
| **GitHub** | `npx -y @modelcontextprotocol/server-github` | `GITHUB_PERSONAL_ACCESS_TOKEN` | Repos, issues, PRs, code search. Use a fine-grained token. |
| **PostgreSQL** | `npx -y @modelcontextprotocol/server-postgres <url>` | a database | Read-only SQL by default; pass a least-privilege role |

### Productivity

| Server | Install | Needs | Notes |
|--------|---------|-------|-------|
| **Notion** | `npx -y @notionhq/notion-mcp-server` | `NOTION_API_TOKEN` | Read/write pages and databases |
| **Slack** | `npx -y @modelcontextprotocol/server-slack` | `SLACK_BOT_TOKEN`, `SLACK_TEAM_ID` | Channel history and messages |

### Trading & market data

| Server | Install | Needs | Notes |
|--------|---------|-------|-------|
| **CCXT** | `npx -y ccxt-mcp` | exchange keys (optional) | Market data across 100+ exchanges. Use **read-only** keys. |
| **Alpaca** | `uvx alpaca-mcp-server` | `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER=true` | Official Alpaca MCP; paper by default |
| **TradingView (community)** | `npx -y tradingview-mcp` | none | Screener/quotes. Community code — review before enabling. |
| **Yahoo Finance (community)** | `uvx mcp-server-yfinance` | `uv` | Quotes and candles. Useful backup to the built-in market tool. |

> The core already has built-in `get_quote`, `get_quotes`, `technical_analysis`,
> `get_news`, `web_search` and `fetch_url`. Add trading MCP servers when you need
> a specific venue, not as a replacement for the risk gate.

---

## Add a custom server

**MCP servers → Add server.**

| Field | stdio | HTTP |
|-------|-------|------|
| Name | label | label |
| Transport | `stdio` | `http` |
| Command | `npx` / `uvx` / path | — |
| Args | one per line, JSON array in the API | — |
| URL | — | `https://host/mcp` |
| Env | `KEY=value` lines | optional auth headers via env |
| Auto-start | start when the core starts | same |
| Category | free text | free text |

Example: a local filesystem server scoped to a notes folder.

```json
{
  "name": "Notes",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:/Users/me/notes"],
  "env": {},
  "enabled": true,
  "auto_start": false,
  "category": "system"
}
```

Environment values are encrypted at rest and only masked in API responses.

### HTTP example

```json
{
  "name": "Remote research",
  "transport": "http",
  "url": "https://mcp.example.com/mcp",
  "env": { "Authorization": "Bearer <token>" },
  "enabled": true,
  "auto_start": true,
  "category": "search"
}
```

The client sends `Accept: application/json, text/event-stream` and handles both
response shapes. A 401 means the auth header is wrong; a 406 means the server
does not implement Streamable HTTP.

---

## Tool naming and approval

Tools are exposed to the model as `server__tool` (for example
`context7__resolve-library-id`). This avoids collisions between servers.

A tool name matching

```
delete|write|create|update|execute|run|send|trade|order|transfer|post|put|patch|remove|drop|kill|install
```

is treated as **state-changing**. Unless **Settings → Auto-execute read-only MCP
tools** is on *and* the tool is classified read-only, the call becomes an
approval card:

```
MCP tool approval
server: filesystem
tool: write_file
args: {"path": "...", "content": "..."}
[Approve] [Reject]
```

Approving runs the tool once and stores the result in the audit log. Rejecting
writes a rejected row and returns an error to the model.

> Approval is a human check, not a sandbox. A server you install can do anything
> your user account can do. Only install servers you trust, and scope filesystem
> and database servers tightly.

---

## Lifecycle and debugging

| Action | Endpoint | Effect |
|--------|----------|--------|
| Start | `POST /api/mcp/{id}/start` | Spawn/connect, `initialize`, `tools/list` |
| Stop | `POST /api/mcp/{id}/stop` | Terminate process or close HTTP client |
| Test | `POST /api/mcp/{id}/test` | Start if needed, call the first tool with `{}` |
| Call | `POST /api/mcp/{id}/call` | Manual `{tool, args}` invocation |
| Edit | `PATCH /api/mcp/{id}` | Updates config; restart required |
| Delete | `DELETE /api/mcp/{id}` | Stops and removes config |

Common errors:

| Message | Cause | Fix |
|---------|-------|-----|
| `spawn npx ENOENT` | Node not on PATH for the core process | Install Node; restart the core |
| `uvx not found` | `uv` missing | `py -3.12 -m pip install uv` |
| `initialize timed out` | Server downloading packages on first run | Wait, or pre-install: `npx -y <pkg> --help` |
| `401` / `403` | Missing or wrong env token | Edit env, restart |
| `Method not found` | Server is older/newer than the client expectation | Check the server version |
| Tool list empty | Server started but exposes no tools | Check its logs on stderr |

The core keeps at most one client per server. A crashed child is detected by
`alive()` and reported as `status=error`; the agent continues without it.

---

## Security checklist

- [ ] Install servers one at a time and read their source or npm page.
- [ ] Prefer official `@modelcontextprotocol/*` and vendor-published packages.
- [ ] Scope filesystem servers to a dedicated folder.
- [ ] Use read-only database roles and exchange API keys.
- [ ] Disable a server when you are not using it.
- [ ] Keep `auto_execute_tools` off unless you fully trust the tool set.
- [ ] Never put a provider key into an MCP server env by habit.
- [ ] Review the audit log after a session with a new server.

---

## Related docs

- [SKILLS_CATALOG.md](SKILLS_CATALOG.md) — playbooks that tell the agent *how* to use tools
- [SECURITY_AND_RISK.md](SECURITY_AND_RISK.md) — the full threat model
- [API_REFERENCE.md](API_REFERENCE.md) — MCP endpoints
