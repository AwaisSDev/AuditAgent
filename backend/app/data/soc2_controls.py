"""F7 — static SOC2 Trust Services Criteria (Common Criteria) mapping.

Not legal or audit advice: this shows a workspace's auditor which of their
AuditAgent-logged evidence *speaks to* each control, as a starting point for
their own SOC2 readiness work — it doesn't certify compliance by itself.
"""

from pydantic import BaseModel


class Soc2Control(BaseModel):
    control_id: str
    title: str
    description: str
    evidence_type: str
    evidence_note: str


SOC2_CONTROLS: list[Soc2Control] = [
    Soc2Control(
        control_id="CC6.1",
        title="Logical access — least privilege",
        description="The entity implements logical access controls to protect systems from unauthorized access.",
        evidence_type="api_keys",
        evidence_note="Per-workspace API keys, individually revocable, with last-used tracking.",
    ),
    Soc2Control(
        control_id="CC6.2",
        title="Access provisioning & de-provisioning",
        description="Access is granted/removed based on authorization, and removed when no longer needed.",
        evidence_type="workspace_members + api_keys",
        evidence_note="Membership roles and API key revocation timestamps show who had access and when it ended.",
    ),
    Soc2Control(
        control_id="CC6.3",
        title="Role-based access",
        description="Access is restricted based on roles and responsibilities.",
        evidence_type="workspace_members.role",
        evidence_note="owner/admin/member roles gate write actions like policy edits and approval decisions.",
    ),
    Soc2Control(
        control_id="CC6.6",
        title="Protection against external threats",
        description="The entity implements controls to prevent or detect unauthorized access from outside its boundaries.",
        evidence_type="events (action_type=external)",
        evidence_note="Every outbound/external agent action is logged and, per policy, gated on human approval.",
    ),
    Soc2Control(
        control_id="CC6.7",
        title="Data transmission & disposal controls",
        description="Data is protected during transmission and removed when no longer needed.",
        evidence_type="redaction pipeline",
        evidence_note="PII is redacted (Presidio + LLM pass) before any event is ever persisted.",
    ),
    Soc2Control(
        control_id="CC7.1",
        title="Detection of security events",
        description="The entity monitors system components for anomalies indicative of malicious acts or errors.",
        evidence_type="events.status = error",
        evidence_note="Failed/erroring agent actions are captured as first-class logged events, filterable in the dashboard.",
    ),
    Soc2Control(
        control_id="CC7.2",
        title="Monitoring for anomalies",
        description="The entity monitors system components and evaluates anomalies against defined thresholds.",
        evidence_type="policies + approvals",
        evidence_note="Policy rules flag anomalous/risky action types for mandatory human review in real time.",
    ),
    Soc2Control(
        control_id="CC7.3",
        title="Incident evaluation",
        description="The entity evaluates security incidents to determine the response required.",
        evidence_type="approvals.status = rejected/denied_timeout",
        evidence_note="Rejected or auto-denied actions form a searchable record of what was stopped, and why.",
    ),
    Soc2Control(
        control_id="CC8.1",
        title="Change management",
        description="Changes to infrastructure, data, and software are authorized, tested, and approved.",
        evidence_type="policies.updated_at",
        evidence_note="Every policy change is timestamped; the previous ruleset is recoverable from workspace history.",
    ),
    Soc2Control(
        control_id="CC9.1",
        title="Risk mitigation",
        description="The entity identifies and manages risks associated with vendors and business partners.",
        evidence_type="agents + policies",
        evidence_note="Each agent's allowed actions are explicit and policy-gated rather than implicitly trusted.",
    ),
    Soc2Control(
        control_id="A1.2",
        title="Availability monitoring",
        description="The entity monitors system capacity and availability against objectives.",
        evidence_type="events.latency_ms",
        evidence_note="Per-action latency is captured on every logged event for trend analysis.",
    ),
    Soc2Control(
        control_id="PI1.1",
        title="Processing integrity",
        description="Data processing is complete, valid, accurate, timely, and authorized.",
        evidence_type="events.row_hash / prev_hash",
        evidence_note="Hash-chained, append-only event rows make undetected retroactive edits computationally infeasible.",
    ),
    Soc2Control(
        control_id="C1.1",
        title="Confidentiality of information",
        description="Confidential information is protected during collection, use, retention, and disposal.",
        evidence_type="events.inputs_redacted / output_redacted",
        evidence_note="Only redacted content is ever stored — raw PII never reaches long-term storage.",
    ),
    Soc2Control(
        control_id="P1.1",
        title="Privacy notice & choice",
        description="The entity provides notice about its privacy practices and obtains consent where required.",
        evidence_type="questionnaires/answers",
        evidence_note="Evidence-pack answers document how agent-collected data is handled, citing specific logged events.",
    ),
    Soc2Control(
        control_id="CC4.1",
        title="Ongoing evaluation of controls",
        description="The entity selects and performs ongoing evaluations to ascertain controls are present and functioning.",
        evidence_type="audit_chain",
        evidence_note="Daily chained checkpoints let an auditor verify the whole log is unaltered as of any given date.",
    ),
]
