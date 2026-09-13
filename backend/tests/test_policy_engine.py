import pytest

from app.services.policy_engine import PolicyParseError, parse_policy, requires_approval


def test_no_rules_means_no_approval_needed():
    policy = parse_policy("rules: []")
    assert requires_approval(policy, {"action_type": "external", "action_name": "anything"}) is False


def test_exact_match_requires_approval():
    policy = parse_policy(
        """
        rules:
          - match:
              action_type: external
            require_approval: true
        """
    )
    assert requires_approval(policy, {"action_type": "external", "action_name": "send_email"}) is True
    assert requires_approval(policy, {"action_type": "internal", "action_name": "summarize"}) is False


def test_wildcard_match_on_action_name():
    policy = parse_policy(
        """
        rules:
          - match:
              action_type: data_access
              action_name: "delete_*"
            require_approval: true
        """
    )
    assert requires_approval(policy, {"action_type": "data_access", "action_name": "delete_user"}) is True
    assert requires_approval(policy, {"action_type": "data_access", "action_name": "read_user"}) is False


def test_first_matching_rule_wins():
    policy = parse_policy(
        """
        rules:
          - match:
              action_type: external
            require_approval: false
          - match:
              action_type: external
            require_approval: true
        """
    )
    assert requires_approval(policy, {"action_type": "external", "action_name": "anything"}) is False


def test_invalid_yaml_raises_policy_parse_error():
    with pytest.raises(PolicyParseError):
        parse_policy("rules: [this is not: valid: yaml:")


def test_invalid_schema_raises_policy_parse_error():
    # `require_approval` must be a bool, and `match` must be a dict of strings.
    with pytest.raises(PolicyParseError):
        parse_policy(
            """
            rules:
              - match: "not-a-dict"
                require_approval: true
            """
        )
