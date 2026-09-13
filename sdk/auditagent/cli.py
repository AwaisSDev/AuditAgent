"""``auditagent`` command-line tool.

Lets a developer validate their `auditagent.policy.yaml` (the same file
passed to `AuditAgent(policy_yaml=...)` — see README's "Policy" section)
before ever deploying it, and check what a given action would resolve to
under it. Both commands run entirely offline: no API key, no network call.

    $ auditagent validate auditagent.policy.yaml
    $ auditagent check auditagent.policy.yaml --action-type external --action-name send_email
"""

from __future__ import annotations

import argparse
import sys
from fnmatch import fnmatch
from typing import Any

import yaml

from auditagent.policy import Policy

_ALLOWED_MATCH_FIELDS = {"action_type", "action_name"}


class PolicyValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_policy_yaml(rules_yaml: str) -> list[dict]:
    """Parses and structurally validates a policy YAML document, raising
    `PolicyValidationError` with every problem found (not just the first) if
    it's invalid. Mirrors the schema backend/app/services/policy_engine.py
    enforces server-side — the SDK's own `Policy` class is deliberately
    lenient at runtime (silently treats a malformed rule as "no match"
    rather than raising, so one bad rule can't crash the host process), so
    this is the strict counterpart for catching mistakes before they ship.
    """
    try:
        parsed = yaml.safe_load(rules_yaml)
    except yaml.YAMLError as exc:
        raise PolicyValidationError([f"Invalid YAML: {exc}"]) from exc

    if parsed is None:
        raise PolicyValidationError(['Empty document — expected at least a top-level "rules:" key.'])
    if not isinstance(parsed, dict):
        raise PolicyValidationError([f"Top level must be a mapping with a 'rules' key, got {type(parsed).__name__}."])

    rules = parsed.get("rules", [])
    if not isinstance(rules, list):
        raise PolicyValidationError([f"'rules' must be a list, got {type(rules).__name__}."])

    errors: list[str] = []
    for i, rule in enumerate(rules):
        prefix = f"rules[{i}]"
        if not isinstance(rule, dict):
            errors.append(f"{prefix}: must be a mapping, got {type(rule).__name__}.")
            continue

        match = rule.get("match")
        if not isinstance(match, dict):
            errors.append(f"{prefix}.match: must be a mapping, got {type(match).__name__ if match is not None else 'missing'}.")
        else:
            for field, pattern in match.items():
                if field not in _ALLOWED_MATCH_FIELDS:
                    errors.append(f"{prefix}.match: unknown field '{field}' (expected one of {sorted(_ALLOWED_MATCH_FIELDS)}).")
                if not isinstance(pattern, str):
                    errors.append(f"{prefix}.match.{field}: must be a string, got {type(pattern).__name__}.")

        if "require_approval" in rule and not isinstance(rule["require_approval"], bool):
            errors.append(f"{prefix}.require_approval: must be true/false, got {type(rule['require_approval']).__name__}.")

    if errors:
        raise PolicyValidationError(errors)
    return rules


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        print(f"Couldn't read {args.file}: {exc}", file=sys.stderr)
        return 2

    try:
        rules = validate_policy_yaml(text)
    except PolicyValidationError as exc:
        print(f"FAIL: {args.file} is invalid:", file=sys.stderr)
        for e in exc.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK: {args.file} is valid ({len(rules)} rule{'s' if len(rules) != 1 else ''}).")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    try:
        with open(args.file, encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        print(f"Couldn't read {args.file}: {exc}", file=sys.stderr)
        return 2

    try:
        validate_policy_yaml(text)
    except PolicyValidationError as exc:
        print(f"FAIL: {args.file} is invalid, can't evaluate it:", file=sys.stderr)
        for e in exc.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    policy = Policy(text)
    needs_approval = policy.requires_approval(args.action_type, args.action_name)
    matched_rule = _first_matching_rule(policy.rules, args.action_type, args.action_name)

    verdict = "needs approval" if needs_approval else "runs automatically"
    print(f"{args.action_type}/{args.action_name} -> {verdict}")
    if matched_rule is not None:
        print(f"  matched: {matched_rule.get('match')}")
    else:
        print("  matched: (no rule matched - default is to run automatically)")
    return 0


def _first_matching_rule(rules: list[dict], action_type: str, action_name: str) -> dict[str, Any] | None:
    fields = {"action_type": action_type, "action_name": action_name}
    for rule in rules:
        match = rule.get("match", {})
        if all(field in fields and fnmatch(str(fields[field]), pattern) for field, pattern in match.items()):
            return rule
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="auditagent", description="Offline tools for an auditagent.policy.yaml file.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser("validate", help="Check a policy YAML file for syntax/schema errors.")
    p_validate.add_argument("file", help="Path to the policy YAML file.")
    p_validate.set_defaults(func=_cmd_validate)

    p_check = sub.add_parser("check", help="Show whether a given action would need approval under a policy file.")
    p_check.add_argument("file", help="Path to the policy YAML file.")
    p_check.add_argument("--action-type", required=True)
    p_check.add_argument("--action-name", required=True)
    p_check.set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
