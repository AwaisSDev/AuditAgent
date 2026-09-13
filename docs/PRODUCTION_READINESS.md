# Production readiness

What's been verified this pass, and what's left that only you can decide or
provision (a business/vendor choice, not a code gap). Dated 2026-09-13.

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

- **Stripe products/prices** — `STRIPE_SECRET_KEY` and the three price IDs
  are unset in the real environment used this session. The checkout flow
  now fails *cleanly* (a real bug fixed this session — see prior summary),
  but nobody can actually subscribe until you create the products in your
  own Stripe dashboard and set the env vars (`docs/MANUAL_SETUP.md` already
  documents the exact steps).
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
  customers, not something inferable from the code.
- **Cross-browser / real-device testing** — this session's testing ran in
  one Chromium-based sandboxed preview. It's a reasonable proxy for mobile
  Safari/Chrome layout (same rendering engine family for Chrome, and the
  CSS here uses no engine-specific features), but isn't a substitute for
  an actual iPhone/Android pass before a real launch.

## Suggested order if you want to keep going

1. Decide on Stripe/Slack/error-tracking now if you want them live for
   launch, since each is a vendor signup + a few env vars, not a code
   change.
2. A real-device pass (one iPhone Safari, one Android Chrome) on the
   signup -> workspace -> SDK event -> approval -> questionnaire flow this
   session already validated against real infra.
3. Decide your retention/support/SLA posture before advertising it anywhere
   — that's a business decision this document can't make for you.
