# Getting started with Tracyn

This is the walkthrough for a new customer, start to finish: sign up, log
your first agent action, and get a human into the approval loop. Every step
below is something you can actually click through today — it isn't a
roadmap.

## 1. Create your account and workspace

1. Go to `https://tracyn.online` and sign in with your work email
   (magic link — no password to set).
2. On first login you'll be asked to name a workspace. One workspace per
   team/product is typical; you can create more later from the workspace
   switcher in the sidebar.

## 2. Get an API key

1. In the dashboard, open **Settings → API Keys**.
2. Click **Create key**, give it a name that says where it'll live (e.g.
   `prod-checkout-agent`), and copy the value shown — it's only shown once.
3. Store it as an environment variable (`TRACYN_API_KEY`) wherever your
   agent runs. Never commit it to source control.

## 3. Install the SDK

```bash
pip install tracyn
```

```python
from tracyn import Tracyn

audit = Tracyn(api_key="TRACYN_API_KEY", agent_name="billing-bot")

@audit.track(action_type="external", action_name="send_refund")
def send_refund(customer_id: str, amount_cents: int):
    ...  # your existing function, unchanged
```

That's the whole integration for logging. `audit.track` wraps your existing
function — it doesn't change what the function does or returns, it just
reports that the call happened. Inputs/outputs are redacted for common PII
(and, as a second pass, secrets/API keys an automated filter catches) on
the server as the event is ingested — nothing is sent to a customer or
third party unredacted.

Run your agent once and check **Dashboard → Timeline** in the app — you
should see the event appear within a few seconds.

## 4. Decide what needs a human (Policy)

Most actions don't need a human in the loop. Some — refunds over a
threshold, emails to customers, anything destructive — should. That's what
**Policy** (in the sidebar) configures:

```yaml
rules:
  - match:
      action_name: send_refund
      inputs.amount_cents: { gt: 10000 }
    require_approval: true
```

Once a rule matches, `audit.track` blocks (it polls, it doesn't spin) until
someone approves or rejects from the dashboard, Slack, or the emailed
fallback link — then your function runs (or doesn't, if rejected) and the
result is what your code sees.

## 5. Get approvals into Slack (optional but recommended)

Without Slack configured, pending approvals still work — they show up on
the **Approvals** page and, if you've set a fallback email in Settings, as
an email link. Most teams still want Slack:

1. In **Settings**, follow the "Connect Slack" steps (this asks your admin
   to install the Tracyn Slack app once per workspace).
2. Pick which channel gets approval requests. Anyone in that channel can
   approve or reject with one click.

## 6. Answer a security questionnaire in minutes, not days

Under **Questionnaires**, upload a customer's security/compliance
questionnaire (PDF, DOCX, or plain text). Tracyn parses out individual
questions, finds your actual logged events that are relevant evidence for
each one, and drafts a cited answer. You review and edit every answer
before exporting — nothing goes to a customer without a human reading it
first.

## 7. What to check before you tell a customer you're "SOC 2 ready"

The **SOC 2** page maps common Trust Services Criteria to what Tracyn
is actually logging for you. It's a starting point for your own audit
prep, not a certification — talk to an auditor before making that claim
externally.

## Where to go next

- [`sdk/README.md`](../sdk/README.md) — full SDK reference (async support,
  the CLI's `tracyn validate`/`check` commands for testing policy YAML
  offline, error handling).
- [`SUPPORT.md`](../SUPPORT.md) — how to reach us and what to expect.
- Stuck on something this doc doesn't cover? See Support below — that's
  exactly the kind of gap we want to hear about.
