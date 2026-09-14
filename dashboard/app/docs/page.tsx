import type { Metadata } from "next";
import Link from "next/link";
import { ForceLightTheme } from "@/components/force-light-theme";

export const metadata: Metadata = {
  title: "Docs",
  description:
    "Get an AuditAgent workspace running end to end: install the SDK, set a policy, route approvals to Slack, and answer security questionnaires from your logs.",
};

function Code({ children }: { children: string }) {
  return (
    <pre className="mt-3 overflow-x-auto rounded-md border border-border bg-muted p-3 text-[13px] leading-relaxed">
      <code>{children}</code>
    </pre>
  );
}

function Section({
  step,
  title,
  id,
  children,
}: {
  step: number;
  title: string;
  id?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-8 border-t border-border py-8 first:border-t-0 first:pt-0">
      <div className="flex items-baseline gap-3">
        <span className="text-sm font-medium text-muted-foreground">{step}</span>
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
      </div>
      <div className="mt-3 space-y-3 text-[15px] leading-relaxed text-muted-foreground [&_a]:text-foreground [&_a]:underline [&_a]:underline-offset-2 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-[13px] [&_code]:text-foreground">
        {children}
      </div>
    </section>
  );
}

export default function DocsPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <ForceLightTheme />
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-[720px] items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element -- next/image's optimizer (sharp) fails on this PNG */}
            <img src="/logo.png" alt="" width={22} height={22} />
            <span className="text-[15px] font-semibold tracking-tight">AuditAgent</span>
          </Link>
          <Link
            href="/login"
            className="rounded-full border border-border px-4 py-1.5 text-sm font-medium transition-colors hover:bg-muted"
          >
            Log in
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-[720px] px-6 py-12">
        <h1 className="text-2xl font-bold tracking-tight">Getting started</h1>
        <p className="mt-2 text-[15px] text-muted-foreground">
          This is the walkthrough for a new customer, start to finish. Every step below is something you
          can click through today, not a roadmap.
        </p>

        <div className="mt-8">
          <Section step={1} title="Create your account and workspace">
            <p>
              Go to the app and sign in with your work email (magic link, no password to set). On first
              login you&apos;ll be asked to name a workspace. One workspace per team or product is typical.
            </p>
          </Section>

          <Section step={2} title="Get an API key">
            <p>
              In the dashboard, open <strong>Settings &rarr; API Keys</strong>. Click <strong>Create key</strong>,
              give it a name that says where it&apos;ll live (e.g. <code>prod-checkout-agent</code>), and
              copy the value shown. It&apos;s only shown once, so store it as an environment variable
              (<code>AUDITAGENT_API_KEY</code>) wherever your agent runs.
            </p>
          </Section>

          <Section step={3} title="Install the SDK">
            <p>One decorator is the whole integration for logging:</p>
            <Code>{`pip install AudAgent`}</Code>
            <Code>{`from audagent import AuditAgent

audit = AuditAgent(api_key="AUDITAGENT_API_KEY", agent_name="billing-bot")

@audit.track(action_type="external", action_name="send_refund")
def send_refund(customer_id: str, amount_cents: int):
    ...  # your existing function, unchanged`}</Code>
            <p>
              <code>audit.track</code> wraps your function without changing what it does or returns; it
              just reports that the call happened. Inputs and outputs are redacted for common PII, and a
              second automated pass catches secrets or API keys, before the event is ever stored.
            </p>
          </Section>

          <Section step={4} title="Decide what needs a human">
            <p>
              Most actions don&apos;t need a human in the loop. Some, like refunds over a threshold or
              anything destructive, should. That&apos;s what <strong>Policy</strong> configures:
            </p>
            <Code>{`rules:
  - match:
      action_name: send_refund
      inputs.amount_cents: { gt: 10000 }
    require_approval: true`}</Code>
            <p>
              Once a rule matches, <code>audit.track</code> blocks (it polls, it doesn&apos;t spin) until
              someone approves or rejects, then your function runs, or doesn&apos;t, and the result is what
              your code sees.
            </p>
          </Section>

          <Section step={5} title="Get approvals into Slack">
            <p>
              Without Slack, pending approvals still work: they show up on the Approvals page and, with a
              fallback email set in Settings, as an emailed link. Most teams still connect Slack from
              Settings so anyone in the right channel can approve with one click.
            </p>
          </Section>

          <Section step={6} title="Answer a security questionnaire in minutes">
            <p>
              Under Questionnaires, upload a customer&apos;s security or compliance questionnaire (PDF,
              DOCX, or plain text). AuditAgent parses out individual questions, finds your actual logged
              events that are relevant evidence for each one, and drafts a cited answer. You review and
              edit every answer before exporting; nothing goes to a customer without a human reading it
              first.
            </p>
          </Section>

          <Section step={7} title="What SOC 2 mapping actually gives you">
            <p>
              The SOC 2 page maps common Trust Services Criteria to what AuditAgent is logging for you.
              It&apos;s a starting point for your own audit prep, not a certification. Talk to an auditor
              before making that claim externally.
            </p>
          </Section>

          <Section step={8} id="mcp" title="Ask Claude, ChatGPT, or Grok about your audit trail">
            <p>
              AuditAgent also runs as an MCP server, so you can ask an AI assistant things like
              &ldquo;anything waiting on me?&rdquo; or &ldquo;what did the billing agent do last
              night?&rdquo; directly. It reads the same record as the dashboard, and it can only read.
              Two ways to connect, depending on which assistant:
            </p>
            <p>
              <strong>Claude.ai, ChatGPT, or Grok</strong> (hosted, no install): these run in the browser
              with no local machine to install anything on, so they connect to AuditAgent&apos;s own
              hosted MCP endpoint instead. Add a custom connector pointing at your deployed
              backend&apos;s <code>/mcp</code> path, using your AuditAgent API key as the bearer token
              when prompted.
            </p>
            <p>
              <strong>Claude Desktop or Claude Code</strong> (local): these run as a process on your own
              machine, so they can run the server directly:
            </p>
            <Code>{`pip install auditagent-mcp`}</Code>
            <Code>{`{
  "mcpServers": {
    "auditagent": {
      "command": "auditagent-mcp",
      "env": { "AUDITAGENT_API_KEY": "al_live_..." }
    }
  }
}`}</Code>
          </Section>
        </div>

        <div className="mt-4 border-t border-border pt-8 text-[15px] text-muted-foreground">
          <p>
            The SDK also ships an offline <code>audagent</code> CLI for validating a policy file before
            it ships, and supports async functions the same way as sync ones. Stuck on something not
            covered here? Email{" "}
            <a href="mailto:support@auditagent.dev" className="text-foreground underline underline-offset-2">
              support@auditagent.dev
            </a>
            . That&apos;s exactly the kind of gap we want to hear about.
          </p>
        </div>
      </main>
    </div>
  );
}
