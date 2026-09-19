# Privacy Policy — DRAFT TEMPLATE, NOT LEGAL ADVICE

> **Read this before using the text below.** This is a generic
> privacy-policy scaffold describing what the Tracyn codebase actually
> does with data today — it is not a finished legal document and not legal
> advice. If you'll have customers in the EU/UK/California or other
> regulated jurisdictions, you likely need a DPA (Data Processing
> Agreement), an SCC/adequacy mechanism for cross-border transfer, and
> jurisdiction-specific disclosures (GDPR Article 13/14, CCPA) that this
> template does not attempt to provide. Have a licensed lawyer review this
> before publishing it.

---

## Privacy Policy

**Last updated:** `[date]`

This Privacy Policy describes how `[Company Name]` ("we", "us") handles
information in connection with the Tracyn Service.

### 1. What we collect

- **Account information:** your email address (used for magic-link sign-in
  via Supabase Auth), and the workspace(s) you create or join.
- **Logged agent events (Customer Data):** action names, timestamps, and
  input/output previews your SDK integration sends us. This is redacted
  in two passes before storage — a pattern/NER-based filter (Presidio) for
  structured PII (names, emails, phone numbers, SSNs, card numbers), then
  a second automated pass (an Anthropic Claude model) for anything the
  first pass misses, such as API keys or internal identifiers mentioned in
  free text. Neither pass is a guarantee that all sensitive data is
  caught — see §5.
- **Uploaded questionnaires (F4):** files you upload are stored in a
  private Supabase Storage bucket and processed to draft answers; you
  control export and never a third party without your action.
- **Billing information:** handled entirely by Whop — we store your
  Whop membership ID, not your card details.
- **Usage/log data:** standard web server logs (IP, user agent, request
  path) for security and debugging.

### 2. How we use it

To operate, maintain, and improve the Service; to communicate with you
about your account, approvals awaiting a decision, or service changes; to
process payment (via Whop); and to comply with legal obligations.

We do not sell Customer Data, and we do not use it to train models beyond
what's needed to generate your own questionnaire answers and redaction
passes at the time you use those features.

### 3. Sub-processors (who else touches your data)

| Sub-processor | Purpose                                   | Data involved |
|----------------|--------------------------------------------|----------------|
| Supabase       | Database, authentication, file storage      | All account and Customer Data |
| Anthropic      | Second-pass redaction (Haiku), questionnaire answer drafting (Sonnet) | Event content sent for redaction/drafting only |
| Resend         | Transactional email (approval requests, timeout notices) | Recipient email, agent/action names |
| Slack          | Approval notifications (only if you connect it) | Agent/action names, your workspace's chosen channel |
| Whop           | Payment processing | Billing contact info, subscription status |
| `[Railway / your host]` | Application hosting | All of the above, in transit/at rest |

`[Keep this table in sync with reality — if you add or remove a vendor,
update this list and, depending on your contracts, notify customers per
whatever change-notice period you commit to in §7.]`

### 4. Data retention and deletion

Customer Data is retained for as long as your account is active. On
account closure, we retain data for `[e.g. 30 days]` to allow export, then
delete it. `[Decide your actual backup-retention tail — most databases
keep deleted data in backups for some window after a logical delete;
state that window honestly rather than implying instant erasure.]`

### 5. Security

Data is encrypted in transit (TLS) and at rest (via our infrastructure
providers). The `events` table is append-only at the database level — a
trigger rejects `UPDATE`/`DELETE` — so even a compromised application
credential cannot alter or erase logged history. Automated redaction (§1)
reduces but does not eliminate the chance that sensitive data appears in
what you log; you're responsible for not intentionally logging data your
own policies prohibit collecting.

### 6. Your rights

Depending on your jurisdiction, you may have rights to access, correct,
export, or delete your personal data. Contact `[privacy@tracyn.online]`
to exercise these. `[If you'll serve EU/UK/California residents, this
section needs the specific GDPR/CCPA rights language and response-time
commitments those laws require — a generic paragraph isn't sufficient on
its own.]`

### 7. Changes to this policy

We'll post updates here and, for material changes, notify you via
`[email/in-product notice]`.

### 8. Contact

`[Company Name]`, `[address]` — `[privacy@tracyn.online]`
