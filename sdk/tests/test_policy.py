from audagent.policy import Policy


def test_no_rules_means_no_approval_needed():
    policy = Policy("rules: []")
    assert policy.requires_approval("external", "anything") is False


def test_exact_match_requires_approval():
    policy = Policy(
        """
        rules:
          - match:
              action_type: external
            require_approval: true
        """
    )
    assert policy.requires_approval("external", "send_email") is True
    assert policy.requires_approval("internal", "summarize") is False


def test_wildcard_match_on_action_name():
    policy = Policy(
        """
        rules:
          - match:
              action_type: data_access
              action_name: "delete_*"
            require_approval: true
        """
    )
    assert policy.requires_approval("data_access", "delete_user") is True
    assert policy.requires_approval("data_access", "read_user") is False


def test_first_matching_rule_wins():
    policy = Policy(
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
    assert policy.requires_approval("external", "anything") is False


def test_default_policy_flags_external():
    policy = Policy.default()
    assert policy.requires_approval("external", "anything") is True
    assert policy.requires_approval("internal", "anything") is False
