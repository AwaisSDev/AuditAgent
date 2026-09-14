# auditagent

Drop-in logging, human approvals, and compliance evidence for AI agents.

```bash
pip install AudAgent
```

```python
from auditagent import AuditAgent

audit = AuditAgent(api_key="al_live_...", agent_name="support-bot")

@audit.track(action_type="external", action_name="send_email")
async def send_email(to: str, subject: str, body: str):
    return await email_provider.send(to, subject, body)
```

That's it — every call to `send_email` is now logged (inputs, output, latency,
cost, model, a hash of the prompt) with PII redacted server-side before
storage. If your workspace's policy requires approval for `action_type:
external`, the call blocks until a human approves/rejects/edits it in Slack
(or via email if Slack isn't configured) — see your dashboard's Policy tab.

## Handling rejections

```python
from auditagent import ApprovalDeniedError, ApprovalTimeoutError

try:
    await send_email("customer@example.com", "Refund approved", "...")
except ApprovalDeniedError as e:
    print(f"Blocked by {e.decision_by}: {e.note}")
except ApprovalTimeoutError:
    print("Nobody responded in time — treated as denied")
```

## Shutting down cleanly

Logging happens on a background thread so `track()` adds well under 5ms to
the wrapped call. `AuditAgent` registers an `atexit` hook automatically, so
queued events are flushed on normal process exit without any extra setup.

If you want the queue drained at a specific point instead of waiting for
exit — e.g. before a health check reports ready, or between batches in a
long-running worker — call `audit.flush()` or `audit.close()` yourself
(both are safe to call more than once).

## Policy

By default the SDK fetches your workspace's active policy from the
dashboard at startup. To pin a repo-local policy instead (e.g. for CI, or to
review policy changes via pull request):

```python
audit = AuditAgent(
    api_key="al_live_...",
    agent_name="support-bot",
    policy_yaml=open("auditagent.policy.yaml").read(),
)
```

```yaml
# auditagent.policy.yaml
rules:
  - match:
      action_type: external
    require_approval: true
  - match:
      action_type: data_access
      action_name: "delete_*"
    require_approval: true
```

Validate that file (schema + YAML syntax) before committing it, and check
what a given action would resolve to under it — both run offline, no API
key needed:

```bash
auditagent validate auditagent.policy.yaml
auditagent check auditagent.policy.yaml --action-type external --action-name send_email
```

## What this does *not* do

Policy enforcement is trust-based: `track()` checks the policy and calls the
approval endpoint itself, but nothing stops a developer from not wrapping a
call, or from bypassing the SDK entirely in their own code. AuditAgent's
threat model is "give honest teams a governance trail and a real approval
gate," not "prevent a malicious developer from evading their own compliance
tooling." Treat AuditAgent as you would any other internal logging library.
