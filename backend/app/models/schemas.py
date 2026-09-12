from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Ingest (F1 — SDK -> backend)
# ---------------------------------------------------------------------------

class EventIn(BaseModel):
    agent_name: str
    action_type: str
    action_name: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    output: Any = None
    model: str | None = None
    prompt_hash: str | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    # The SDK already resolved any required approval (it blocked on
    # /v1/approvals/request -> poll -> decision) before calling ingest, so it
    # reports the final outcome directly rather than the backend inferring it.
    status: Literal["completed", "approved", "rejected", "denied_timeout", "error"] = "completed"
    approval_id: str | None = None


class EventIngestResponse(BaseModel):
    intake_id: str
    accepted: bool = True


class ApprovalRequestIn(BaseModel):
    agent_name: str
    action_type: str
    action_name: str
    inputs_preview: dict[str, Any] = Field(default_factory=dict)


class ApprovalRequestOut(BaseModel):
    approval_id: str
    status: Literal["pending"]
    expires_at: datetime


class ApprovalStatusOut(BaseModel):
    id: str
    status: Literal["pending", "approved", "rejected", "denied_timeout"]
    decision_by: str | None
    decision_note: str | None
    expires_at: datetime


class EventOut(BaseModel):
    id: str
    workspace_id: str
    agent_id: str | None
    action_type: str
    action_name: str
    inputs_redacted: dict[str, Any]
    output_redacted: Any
    model: str | None
    prompt_hash: str | None
    cost_usd: float | None
    latency_ms: int | None
    status: str
    created_at: datetime
    row_hash: str
    prev_hash: str


# ---------------------------------------------------------------------------
# Policies (F2)
# ---------------------------------------------------------------------------

class PolicyIn(BaseModel):
    name: str = "default"
    rules_yaml: str


class PolicyOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    rules_yaml: str
    is_active: bool
    updated_at: datetime


# ---------------------------------------------------------------------------
# Approvals (F3)
# ---------------------------------------------------------------------------

class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    decision_by: str
    decision_note: str | None = None
    edited_action: dict[str, Any] | None = None


class ApprovalOut(BaseModel):
    id: str
    workspace_id: str
    event_id: str | None  # null until the SDK's ingest call links it (see schema.sql's approvals.event_id comment)
    agent_id: str | None
    requested_action: dict[str, Any]
    status: str
    decision_by: str | None
    decision_note: str | None
    requested_at: datetime
    decided_at: datetime | None
    expires_at: datetime


# ---------------------------------------------------------------------------
# Agents / API keys
# ---------------------------------------------------------------------------

class AgentIn(BaseModel):
    name: str
    description: str | None = None


class AgentOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime


class ApiKeyCreateIn(BaseModel):
    name: str


class ApiKeyCreateOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    full_key: str  # only ever returned once, at creation time


class ApiKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


# ---------------------------------------------------------------------------
# Questionnaires / Evidence packs (F4)
# ---------------------------------------------------------------------------

class QuestionnaireOut(BaseModel):
    id: str
    workspace_id: str
    filename: str
    file_type: str
    status: str
    error_message: str | None
    created_at: datetime


class AnswerOut(BaseModel):
    id: str
    questionnaire_id: str
    question_text: str
    draft_answer: str | None
    final_answer: str | None
    status: str
    evidence_event_ids: list[str] = Field(default_factory=list)


class AnswerUpdateIn(BaseModel):
    final_answer: str
    status: Literal["reviewed", "approved"] = "reviewed"


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

class WorkspaceCreateIn(BaseModel):
    name: str


class WorkspaceOut(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    slack_channel_id: str | None = None
    notify_email: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Billing (F9)
# ---------------------------------------------------------------------------

class CheckoutSessionIn(BaseModel):
    plan: Literal["starter", "growth", "enterprise"]


class CheckoutSessionOut(BaseModel):
    checkout_url: str
