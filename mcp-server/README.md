# auditagent-mcp

An MCP server exposing your AuditAgent workspace as four tools:
`get_recent_actions`, `get_pending_approvals`, `draft_questionnaire_answers`,
`get_compliance_summary`. Works from Claude, ChatGPT, Grok, or any other MCP
client — two different ways to connect, depending on which:

## Option A — hosted (Claude.ai web/mobile, ChatGPT, Grok)

These are hosted chat products with no local machine to run a server on, so
they can only reach a server over the network, not installed via pip. This
server is already mounted at `/mcp` on the deployed backend (see
`backend/app/main.py`) — add `<your backend's base URL>/mcp` as a custom
connector, e.g. this deployment's Hugging Face Space:
`https://awais1290-auditagent.hf.space/mcp`:

- **Claude.ai**: Settings → Connectors → Add custom connector → paste the URL,
  and use your AuditAgent API key (Settings → API keys in the dashboard) as
  the bearer token when prompted.
- **ChatGPT**: Settings → Connectors → Developer mode (Plus/Pro and up) → add
  a custom connector with the same URL and bearer token.
- **Grok**: grok.com/connectors → New Connector → Custom → same URL and
  bearer token.

Each connection authenticates as your own workspace — nothing is shared
between different users of the hosted server.

## Option B — local (Claude Desktop, Claude Code)

These run as a local process on your own machine, so they can spawn this
server directly instead of connecting to the hosted one.

```bash
pip install auditagent-mcp
```

Get a workspace API key from **Settings → API keys** in the AuditAgent
dashboard, then set:

```bash
export AUDITAGENT_API_KEY=al_live_...
export AUDITAGENT_BASE_URL=https://awais1290-auditagent.hf.space   # optional, this is the default
```

Add to your MCP config (Claude Desktop: `claude_desktop_config.json`; Claude
Code: `.mcp.json` or `claude mcp add`):

```json
{
  "mcpServers": {
    "auditagent": {
      "command": "auditagent-mcp",
      "env": {
        "AUDITAGENT_API_KEY": "al_live_..."
      }
    }
  }
}
```

## Using it

Once connected (either option), ask things like:

> "What agent actions happened in the last hour?"
> "Are there any approvals waiting on me?"
> "Draft an answer to: do you log all AI agent actions taken on customer data?"
> "What's our current compliance posture?"

## Manual setup: getting listed for organic discovery

Two separate, unrelated listings — do either or both:

- **The official MCP Registry** (`registry.modelcontextprotocol.io`, a
  community-run metadata index, not an Anthropic product): install the
  `mcp-publisher` CLI, run `mcp-publisher init` to generate a `server.json`,
  `mcp-publisher login github`, then `mcp-publisher publish`. This is what
  makes any MCP-aware client or aggregator find this server by name.
- **Anthropic's own Connectors Directory** (the curated list inside
  claude.ai/Claude Desktop/Claude Code's own UI): a separate submission
  through `https://claude.ai/admin-settings/directory/submissions/new`
  (remote servers like this one; needs a Team/Enterprise claude.ai org) —
  requires a documentation URL, a privacy policy URL, and OAuth for any
  authenticated action (this server currently uses a static bearer token
  instead, which the portal may or may not accept as-is; check its current
  requirements before submitting).

Both are manual, one-time submissions tied to your own identity/ownership —
not something this repo automates.
