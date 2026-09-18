import type { Metadata } from "next";
import { SITE_URL } from "@/lib/site";
import { LegalPage, H2, P, Ul } from "@/components/legal/legal-page";

const TITLE = "Privacy Policy";
const DESCRIPTION =
  "How AuditAgent collects, uses, and protects data when you use our compliance infrastructure for AI agent teams.";
const LAST_UPDATED = "September 18, 2026";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: `${SITE_URL}/privacy` },
  openGraph: {
    title: `${TITLE} / AuditAgent`,
    description: DESCRIPTION,
    url: `${SITE_URL}/privacy`,
    siteName: "AuditAgent",
    images: [{ url: "/logo.png", width: 512, height: 512 }],
    type: "website",
  },
  twitter: { card: "summary", title: `${TITLE} / AuditAgent`, description: DESCRIPTION, images: ["/logo.png"] },
};

export default function PrivacyPolicyPage() {
  return (
    <LegalPage title={TITLE} lastUpdated={LAST_UPDATED}>
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "WebPage",
            name: "AuditAgent Privacy Policy",
            url: `${SITE_URL}/privacy`,
            isPartOf: { "@type": "WebSite", name: "AuditAgent", url: SITE_URL },
            dateModified: "2026-09-18",
          }),
        }}
      />

      <P>
        This Privacy Policy describes how AuditAgent (&ldquo;we&rdquo;, &ldquo;us&rdquo;) handles
        information in connection with the AuditAgent Service. AuditAgent is currently operated by
        an individual rather than a registered legal entity; contact details are in §8.
      </P>

      <H2>1. What we collect</H2>
      <Ul>
        <li>
          <strong>Account information:</strong> your email address (used for sign-in via Supabase
          Auth) and the workspace(s) you create or join.
        </li>
        <li>
          <strong>Logged agent events (Customer Data):</strong> action names, timestamps, and
          input/output previews your SDK integration sends us. This is redacted in two passes
          before storage: a pattern/NER-based filter (Presidio) for structured PII (names,
          emails, phone numbers, SSNs, card numbers), then a second automated pass (an Anthropic
          Claude model) for anything the first pass misses, such as API keys or internal
          identifiers mentioned in free text. Neither pass guarantees all sensitive data is
          caught, see §5.
        </li>
        <li>
          <strong>Uploaded questionnaires:</strong> files you upload are stored in a private
          Supabase Storage bucket and processed to draft answers; you control export.
        </li>
        <li>
          <strong>Billing information:</strong> handled entirely by Whop, we store your Whop
          membership ID, not your card details.
        </li>
        <li>
          <strong>Usage/log data:</strong> standard web server logs (IP, user agent, request path)
          for security and debugging.
        </li>
      </Ul>

      <H2>2. How we use it</H2>
      <P>
        To operate, maintain, and improve the Service; to communicate with you about your
        account, approvals awaiting a decision, or service changes; to process payment (via
        Whop); and to comply with legal obligations.
      </P>
      <P>
        We do not sell Customer Data, and we do not use it to train models beyond what&rsquo;s
        needed to generate your own questionnaire answers and redaction passes at the time you
        use those features.
      </P>

      <H2>3. Sub-processors (who else touches your data)</H2>
      <Ul>
        <li>
          <strong>Supabase:</strong> database, authentication, file storage. All account and
          Customer Data.
        </li>
        <li>
          <strong>Anthropic:</strong> second-pass redaction and questionnaire answer drafting.
          Event content sent for redaction/drafting only.
        </li>
        <li>
          <strong>Resend:</strong> transactional email (approval requests, timeout notices).
          Recipient email, agent/action names.
        </li>
        <li>
          <strong>Slack:</strong> approval notifications, only if you connect it. Agent/action
          names, your workspace&rsquo;s chosen channel.
        </li>
        <li>
          <strong>Whop:</strong> payment processing. Billing contact info, subscription status.
        </li>
        <li>
          <strong>Vercel:</strong> dashboard hosting. Application traffic in transit.
        </li>
        <li>
          <strong>Hugging Face:</strong> backend/API hosting. All of the above, in transit/at
          rest.
        </li>
      </Ul>

      <H2>4. Data retention and deletion</H2>
      <P>
        Customer Data is retained for as long as your account is active. On account closure, we
        retain data for 30 days to allow export, then delete it. Deleted data may persist in
        infrastructure backups for a limited window afterward before those backups themselves
        expire.
      </P>

      <H2>5. Security</H2>
      <P>
        Data is encrypted in transit (TLS) and at rest (via our infrastructure providers). The
        events table is append-only at the database level (a trigger rejects UPDATE/DELETE), so
        even a compromised application credential cannot alter or erase logged history. Automated
        redaction (§1) reduces but does not eliminate the chance that sensitive data appears in
        what you log; you&rsquo;re responsible for not intentionally logging data your own
        policies prohibit collecting.
      </P>

      <H2>6. Your rights</H2>
      <P>
        Depending on your jurisdiction, you may have rights to access, correct, export, or delete
        your personal data. Contact us at the address in §8 to exercise these.
      </P>

      <H2>7. Changes to this policy</H2>
      <P>
        We&rsquo;ll post updates here and, for material changes, notify you via email or an
        in-product notice.
      </P>

      <H2>8. Contact</H2>
      <P>
        AuditAgent, <a href="mailto:mawais9171@gmail.com" className="underline">mawais9171@gmail.com</a>
      </P>
    </LegalPage>
  );
}
