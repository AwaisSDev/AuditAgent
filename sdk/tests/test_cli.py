import pytest

from auditagent.cli import PolicyValidationError, main, validate_policy_yaml

VALID_YAML = """
rules:
  - match:
      action_type: external
    require_approval: true
  - match:
      action_type: data_access
      action_name: "delete_*"
    require_approval: true
"""


def test_validate_accepts_a_well_formed_policy():
    rules = validate_policy_yaml(VALID_YAML)
    assert len(rules) == 2


def test_validate_accepts_empty_rules_list():
    assert validate_policy_yaml("rules: []") == []


def test_validate_rejects_invalid_yaml():
    with pytest.raises(PolicyValidationError, match="Invalid YAML"):
        validate_policy_yaml("rules: [this is not: valid: yaml: [[[")


def test_validate_rejects_non_mapping_top_level():
    with pytest.raises(PolicyValidationError, match="Top level must be a mapping"):
        validate_policy_yaml("- just\n- a\n- list\n")


def test_validate_rejects_rules_not_a_list():
    with pytest.raises(PolicyValidationError, match="'rules' must be a list"):
        validate_policy_yaml("rules: not-a-list")


def test_validate_rejects_match_not_a_mapping():
    with pytest.raises(PolicyValidationError, match="match: must be a mapping"):
        validate_policy_yaml("rules:\n  - match: external\n    require_approval: true\n")


def test_validate_rejects_unknown_match_field():
    with pytest.raises(PolicyValidationError, match="unknown field"):
        validate_policy_yaml("rules:\n  - match:\n      workspace_id: abc\n    require_approval: true\n")


def test_validate_rejects_non_bool_require_approval():
    with pytest.raises(PolicyValidationError, match="must be true/false"):
        validate_policy_yaml('rules:\n  - match:\n      action_type: external\n    require_approval: "yes"\n')


def test_validate_reports_every_error_not_just_the_first():
    bad = "rules:\n  - match: not-a-dict\n    require_approval: 5\n"
    with pytest.raises(PolicyValidationError) as exc_info:
        validate_policy_yaml(bad)
    assert len(exc_info.value.errors) == 2


def test_cli_validate_command_exit_codes(tmp_path):
    good = tmp_path / "good.yaml"
    good.write_text(VALID_YAML)
    assert main(["validate", str(good)]) == 0

    bad = tmp_path / "bad.yaml"
    bad.write_text("rules: not-a-list")
    assert main(["validate", str(bad)]) == 1

    assert main(["validate", str(tmp_path / "missing.yaml")]) == 2


def test_cli_check_command_reports_verdict(tmp_path, capsys):
    f = tmp_path / "policy.yaml"
    f.write_text(VALID_YAML)

    assert main(["check", str(f), "--action-type", "external", "--action-name", "send_email"]) == 0
    out = capsys.readouterr().out
    assert "needs approval" in out

    assert main(["check", str(f), "--action-type", "internal", "--action-name", "summarize"]) == 0
    out = capsys.readouterr().out
    assert "runs automatically" in out
