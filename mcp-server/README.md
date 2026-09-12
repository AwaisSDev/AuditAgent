# auditagent-mcp

A Claude MCP server exposing your AuditAgent workspace as four tools:
`get_recent_actions`, `get_pending_approvals`, `draft_questionnaire_answers`,
`get_compliance_summary`.

## Install

```bash
pip install auditagent-mcp
```

## Configure

Get a workspace API key from **Settings → API keys** in the AuditAgent
dashboard, then set:

```bash
export AUDITAGENT_API_KEY=al_live_...
export AUDITAGENT_BASE_URL=https://api.auditagent.dev   # optional, this is the default
```

## Add to Claude Desktop / Claude Code

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

Then ask Claude things like:

> "What agent actions happened in the last hour?"
> "Are there any approvals waiting on me?"
> "Draft an answer to: do you log all AI agent actions taken on customer data?"
> "What's our current compliance posture?"

## Manual setup: listing on the MCP marketplace

Once published to PyPI (see the root `docs/MANUAL_SETUP.md`), submit this
server to the Anthropic MCP directory (https://github.com/modelcontextprotocol/servers
or the in-product marketplace listing flow, whichever is current when you
ship) for organic discovery — this is a manual, one-time submission, not
something this repo can automate.
