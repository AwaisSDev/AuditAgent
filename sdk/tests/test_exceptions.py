from tracyn.exceptions import ApprovalDeniedError, ApprovalTimeoutError


def test_approval_denied_error_message_includes_reviewer_and_note():
    err = ApprovalDeniedError("send_refund", "alice@example.com", "amount too high")
    assert str(err) == "'send_refund' was rejected by alice@example.com: amount too high"
    assert err.action_name == "send_refund"
    assert err.decision_by == "alice@example.com"
    assert err.note == "amount too high"


def test_approval_denied_error_message_without_a_note():
    err = ApprovalDeniedError("send_refund", "alice@example.com", None)
    assert str(err) == "'send_refund' was rejected by alice@example.com"


def test_approval_denied_error_falls_back_to_a_reviewer_when_decision_by_is_missing():
    err = ApprovalDeniedError("send_refund", None, None)
    assert str(err) == "'send_refund' was rejected by a reviewer"


def test_approval_timeout_error_message():
    err = ApprovalTimeoutError("send_refund")
    assert err.action_name == "send_refund"
    assert "send_refund" in str(err)
    assert "approval window" in str(err)
