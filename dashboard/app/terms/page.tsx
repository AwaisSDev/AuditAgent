import type { Metadata } from "next";
import { SITE_URL } from "@/lib/site";
import { LegalPage, H2, P, Ul } from "@/components/legal/legal-page";

const TITLE = "Terms of Service";
const DESCRIPTION =
  "The terms that govern access to and use of AuditAgent, our compliance infrastructure for AI agent teams.";
const LAST_UPDATED = "September 18, 2026";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: `${SITE_URL}/terms` },
  openGraph: {
    title: `${TITLE} / AuditAgent`,
    description: DESCRIPTION,
    url: `${SITE_URL}/terms`,
    siteName: "AuditAgent",
    images: [{ url: "/logo.png", width: 512, height: 512 }],
    type: "website",
  },
  twitter: { card: "summary", title: `${TITLE} / AuditAgent`, description: DESCRIPTION, images: ["/logo.png"] },
};

export default function TermsOfServicePage() {
  return (
    <LegalPage title={TITLE} lastUpdated={LAST_UPDATED}>
      <script
        type="application/ld+json"
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "WebPage",
            name: "AuditAgent Terms of Service",
            url: `${SITE_URL}/terms`,
            isPartOf: { "@type": "WebSite", name: "AuditAgent", url: SITE_URL },
            dateModified: "2026-09-18",
          }),
        }}
      />

      <P>
        These Terms of Service (&ldquo;Terms&rdquo;) govern access to and use of AuditAgent&rsquo;s
        (&ldquo;we&rdquo;, &ldquo;us&rdquo;, &ldquo;our&rdquo;) product (the &ldquo;Service&rdquo;),
        operated at auditagent.cloud. By creating an account or using the Service, you
        agree to these Terms on behalf of yourself and, if applicable, the organization you
        represent (&ldquo;you&rdquo;, &ldquo;Customer&rdquo;). AuditAgent is currently operated by
        an individual rather than a registered legal entity.
      </P>

      <H2>1. The Service</H2>
      <P>
        AuditAgent provides logging, policy enforcement, and evidence-generation tooling for AI
        agent actions, as described on our website and in-product documentation. We may change or
        discontinue features with 30 days&rsquo; notice for material reductions in functionality
        on paid plans.
      </P>

      <H2>2. Accounts</H2>
      <P>
        You&rsquo;re responsible for the security of your account credentials and API keys, and
        for all activity under your account. Notify us promptly at the address in §12 if you
        suspect unauthorized access.
      </P>

      <H2>3. Customer Data</H2>
      <P>
        &ldquo;Customer Data&rdquo; means the data you submit to the Service, including logged
        agent events, policy configuration, and uploaded questionnaires. As between the parties,
        you own Customer Data. You grant us a license to process it solely to provide, maintain,
        and improve the Service, and as described in our{" "}
        <a href="/privacy" className="underline">
          Privacy Policy
        </a>
        .
      </P>
      <P>
        You&rsquo;re responsible for having the right to submit any data you send us, including
        ensuring you don&rsquo;t submit data you&rsquo;re not permitted to share (e.g. under a
        customer&rsquo;s own confidentiality terms) beyond what&rsquo;s needed for the Service to
        function.
      </P>

      <H2>4. Acceptable use</H2>
      <P>You won&rsquo;t use the Service to:</P>
      <Ul>
        <li>violate applicable law;</li>
        <li>store or transmit malicious code;</li>
        <li>attempt to access another customer&rsquo;s workspace; or</li>
        <li>circumvent usage limits associated with your plan.</li>
      </Ul>

      <H2>5. Fees and payment</H2>
      <P>
        Paid plans are billed monthly in advance via Whop. Fees are non-refundable except as
        required by law or as we agree in writing. We may change pricing with 30 days&rsquo;
        notice, effective at your next billing cycle.
      </P>

      <H2>6. Term and termination</H2>
      <P>
        These Terms remain in effect while you have an active account. Either party may terminate
        for convenience with 30 days&rsquo; notice; we may suspend or terminate immediately for a
        material breach, non-payment, or suspected fraud/abuse. On termination, we&rsquo;ll make
        Customer Data available for export for 30 days, after which it may be deleted.
      </P>

      <H2>7. Confidentiality</H2>
      <P>
        Each party will protect the other&rsquo;s confidential information with the same care it
        uses for its own similar information, and not less than reasonable care, and will use it
        only to perform under these Terms.
      </P>

      <H2>8. Warranties and disclaimers</H2>
      <P>
        THE SERVICE IS PROVIDED &ldquo;AS IS.&rdquo; TO THE MAXIMUM EXTENT PERMITTED BY LAW, WE
        DISCLAIM ALL WARRANTIES, EXPRESS OR IMPLIED, INCLUDING MERCHANTABILITY, FITNESS FOR A
        PARTICULAR PURPOSE, AND NON-INFRINGEMENT. We do not warrant that the Service will be
        uninterrupted or error-free, or that it satisfies any particular regulatory, compliance,
        or certification requirement (including SOC 2) on its own: the Service assists your
        compliance program, it does not replace your own controls or an independent
        auditor&rsquo;s assessment.
      </P>

      <H2>9. Limitation of liability</H2>
      <P>
        TO THE MAXIMUM EXTENT PERMITTED BY LAW, NEITHER PARTY WILL BE LIABLE FOR INDIRECT,
        INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES. EACH PARTY&rsquo;S TOTAL
        LIABILITY ARISING OUT OF THESE TERMS WILL NOT EXCEED THE FEES PAID BY CUSTOMER TO US IN
        THE 12 MONTHS PRECEDING THE CLAIM.
      </P>

      <H2>10. Governing law and disputes</H2>
      <P>
        <em>
          [Governing law jurisdiction: not yet set. AuditAgent is currently operated by an
          individual rather than a registered company, and this section needs the operator&rsquo;s
          actual country/state of residence before it is legally meaningful. Until then, disputes
          are intended to be resolved by litigation, not arbitration, in the courts of that
          jurisdiction once named.]
        </em>
      </P>

      <H2>11. Changes to these Terms</H2>
      <P>
        We may update these Terms; we&rsquo;ll notify you of material changes via email or an
        in-product notice at least 30 days before they take effect. Continued use after that
        constitutes acceptance.
      </P>

      <H2>12. Contact</H2>
      <P>
        AuditAgent, <a href="mailto:mawais9171@gmail.com" className="underline">mawais9171@gmail.com</a>
      </P>
    </LegalPage>
  );
}
