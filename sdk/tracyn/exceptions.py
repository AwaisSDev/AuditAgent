from __future__ import annotations


class ApprovalDeniedError(Exception):
    """Raised instead of running the wrapped function when a human rejects the action."""

    def __init__(self, action_name: str, decision_by: str | None, note: str | None):
        self.action_name = action_name
        self.decision_by = decision_by
        self.note = note
        super().__init__(f"'{action_name}' was rejected by {decision_by or 'a reviewer'}" + (f": {note}" if note else ""))


class ApprovalTimeoutError(Exception):
    """Raised when nobody responds within the policy's approval window."""

    def __init__(self, action_name: str):
        self.action_name = action_name
        super().__init__(f"'{action_name}' was auto-denied — no response within the approval window")
