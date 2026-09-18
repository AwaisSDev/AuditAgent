# Production readiness

What's been verified this pass, and what's left that only you can decide or
provision (a business/vendor choice, not a code gap). Originally dated
2026-09-13, updated 2026-09-14.

## 2026-09-14 update

- **Every package in the repo now has a real automated test suite,
  verified together in one consolidated run**: backend 196 tests (97%
  line coverage), SDK 40 tests (93% coverage, mypy clean), MCP server 16
  tests (previously zero), dashboard 23 tests (previously zero, via a
  newly-added Vitest setup) plus a clean `tsc --noEmit` and production
  build. 275 tests total, all green together, not just individually.
- **Backend test coverage: 55% → 97%** (192 tests, up from 74). Every
  router and service in the backend is now individually covered at 92%
  or higher (most at 100%) — `worker/tasks.py` (the core F1/F3/F4
  pipeline), every router (`agents`, `auth`, `billing`, `ingest`,
  `mcp_data`, `policies`, `questionnaires`, `slack`, `soc2`,
  `workspaces`, `approvals`, `events`), and every service client
  (`classification`, `email_client`, `slack_client`, `slack_verify`,
  `stripe_client`, `approvals_service`).
- **Three real bugs found (two by writing tests, one by an explicit
  security review pass), all fixed:**
  1. `GET /v1/soc2/controls` had **no authentication check at all** —
     the only unauthenticated route in the entire backend, despite its
     own docstring claiming otherwise. Anyone with the URL could hit it
     with no token. Fixed (`routers/soc2.py`); the dashboard always sent
     a token anyway, so this wasn't user-visible, but the backend itself
     didn't enforce it.
  2. `questionnaire_parser.py`'s numbered-list detection never matched
     the single most common numbering style in real questionnaires —
     `"1. Do you..."`, `"2) Have you..."` — because of how `str.rstrip`
     interacts with a trailing space after the marker. Only 2+ digit
     numbers or a marker glued directly to the text (no space) happened
     to pass. Since F4's entire value proposition is "don't miss a
     question" when parsing an upload, silently dropping every
     single-digit numbered item was a real, customer-facing gap. Fixed
     with a proper regex anchor.
  3. **Cross-tenant IDOR in the approval-decide path** (`services/approvals_service.py`):
     `apply_decision` looked up and updated an approval by `id` alone,
     with no `workspace_id` check anywhere in the query. The dashboard's
     decide endpoint only proves the caller belongs to *some* workspace
     (`require_workspace_member(workspace_id)`) — it never proved the
     `approval_id` in the URL belongs to that same workspace. Any
     authenticated member of any workspace who obtained another tenant's
     approval id (a forwarded Slack message, a log line, anything) could
     approve or reject that tenant's pending action. Found via a targeted
     security-review pass over this session's changes; fixed by scoping
     both the SELECT and the compare-and-swap UPDATE by `workspace_id`
     when the dashboard path supplies one (a mismatch reads as a clean
     404, same as a nonexistent id — it never confirms cross-tenant
     existence). The Slack webhook path is unaffected: it's authenticated
     by Slack's own signature verification, not workspace membership.
- Added customer-facing docs that didn't exist before: a getting-started
  walkthrough ([`docs/GETTING_STARTED.md`](GETTING_STARTED.md)), a support
  page with response-time-target placeholders and a security-reporting
  path ([`SUPPORT.md`](../SUPPORT.md)), and Terms of Service / Privacy
  Policy **drafts** ([`docs/legal/`](legal/)) grounded in what the code
  actually does (the real sub-processor list, the real redaction
  pipeline, the real append-only guarantee) — these still need a licensed
  lawyer's review before they govern a real customer relationship; that
  review is a business step, not a code gap, so it's listed below rather
  than claimed as done.

## Verified working (live, against a real Supabase project)

- **F1 Logging**: SDK -> ingest -> worker -> Supabase, end to end. Hash
  chain (`prev_hash`/`row_hash`) checked link-by-link across every real row
  produced this session — intact. Append-only enforcement confirmed by
  directly attempting `UPDATE`/`DELETE` on `events` — both rejected by the
  database trigger, not just application code.
- **F2 Policy**: toggle in the dashboard, confirmed persisted to Supabase;
  malformed YAML in the advanced editor fails with a readable error, no crash.
- **F3 Approvals**: real approve and reject decisions through the dashboard;
  PII in `inputs_preview` confirmed redacted before storage. The
  decision race-condition fix (two concurrent decisions on one approval)
  was tested with true concurrency (`asyncio.gather` against the real DB) —
  exactly one wins, the other is cleanly rejected, and the SDK's blocking
  call unblocks with the correct outcome either way.
- **F4 Evidence packs**: found the `questionnaires` Storage bucket
  documented as a required manual step (`docs/MANUAL_SETUP.md`) was never
  created — F4 was completely broken. Created it, then found and fixed a
  second bug where drafting without an Anthropic key aborted the *entire*
  file instead of degrading one question at a time. Re-ran the same upload
  live after both fixes: parses, matches evidence, drafts (or degrades)
  every question, exports.
- **F6 MCP server**: all 4 tools called against the live local backend with
  a real API key.
- **Retry logic**: already existed and works as designed — the SDK retries
  transient event-send failures 3x with backoff (`client.py::_send_with_retry`);
  the worker retries transient Supabase transport errors the same way
  (`db.py::run_db`).
- **Webhook handling**: already existed and was included in the security
  review — Slack interactivity (`routers/slack.py`, signature-verified) and
  Stripe (`routers/billing.py`, signature-verified via `construct_webhook_event`).
- **Security**: an independent review pass over this session's full diff
  found zero high-confidence vulnerabilities (see prior summary for what
  was specifically checked: the async-refactor closures, the race-condition
  fix, error-message paths, the new inline theme script, CI secret exposure).
- **Mobile**: no horizontal overflow at 320/375/414px on any of the 9 pages;
  iOS zoom-on-focus fixed (16px form text); touch targets brought to ~44px
  on mobile only; dark/light/system theme toggle wired end-to-end.
- **Automated tests**: 34 backend + 20 SDK, all green; `mypy` clean on the
  SDK; dashboard typechecks and production-builds clean; CI added for all
  four packages and verified locally against a byte-for-byte simulation of
  what it will actually run.

## Not done, and why it's not a code fix

These need an account, a vendor choice, or a business decision from you —
none of them are something to write code for on your behalf:

- ~~Stripe products/prices~~ — superseded: billing moved to Whop
  (`docs/MANUAL_SETUP.md` documents the current setup steps), and it's
  live and working in the Whop sandbox as of this update.
- **Slack app** — `SLACK_BOT_TOKEN`/`SLACK_SIGNING_SECRET` are unset;
  approvals fall back silently to "decide in the dashboard" until you
  install the Slack app (`slack-app/manifest.yaml`, `docs/MANUAL_SETUP.md`).
- **Error tracking (Sentry or similar)** — deliberately not wired up.
  Adding a real SDK call needs a real DSN from an account only you can
  create; a fake/placeholder one would silently no-op or throw, which is
  worse than not having it. This is a five-minute add once you've picked a
  vendor and have a key.
- **Incident response plan / SLA** — these are operational/business
  commitments about *your* team's on-call process and what you promise
  customers, not something inferable from the code. `docs/legal/` and
  `SUPPORT.md` now have drafts with the specific placeholders you need to
  fill in (response-time numbers, status-page choice, on-call process).
- **Legal sign-off on the Terms/Privacy drafts** — `docs/legal/` has
  working drafts grounded in the actual sub-processor list and data flow,
  but every bracketed placeholder and the liability/arbitration sections
  specifically need a licensed lawyer in your jurisdiction before you
  publish them as binding.
- **Cross-browser / real-device testing** — this session's testing ran in
  one Chromium-based sandboxed preview. It's a reasonable proxy for mobile
  Safari/Chrome layout (same rendering engine family for Chrome, and the
  CSS here uses no engine-specific features), but isn't a substitute for
  an actual iPhone/Android pass before a real launch.

## Suggested order if you want to keep going

1. Decide on Slack/error-tracking now if you want them live for launch
   (Whop billing is already live), since each is a vendor signup + a few
   env vars, not a code change.
2. A real-device pass (one iPhone Safari, one Android Chrome) on the
   signup -> workspace -> SDK event -> approval -> questionnaire flow this
   session already validated against real infra.
3. Decide your retention/support/SLA posture before advertising it anywhere
   — that's a business decision this document can't make for you.
