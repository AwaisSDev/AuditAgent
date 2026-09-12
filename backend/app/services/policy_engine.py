"""Evaluates a workspace's policy YAML against an incoming event.

Example policy YAML (this is what devs commit to their repo and what's
mirrored into the `policies` table):

    rules:
      - match:
          action_type: external
        require_approval: true
      - match:
          action_type: data_access
          action_name: "delete_*"
        require_approval: true

Rules are evaluated in order; the first match wins. No match = no approval
required. `match` values support `*` glob wildcards via fnmatch.
"""

from fnmatch import fnmatch
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError


class PolicyRule(BaseModel):
    match: dict[str, str]
    require_approval: bool = True


class PolicyDocument(BaseModel):
    rules: list[PolicyRule] = []


class PolicyParseError(Exception):
    pass


DEFAULT_POLICY_YAML = """\
rules:
  - match:
      action_type: external
    require_approval: true
"""


def parse_policy(rules_yaml: str) -> PolicyDocument:
    try:
        raw = yaml.safe_load(rules_yaml) or {}
    except yaml.YAMLError as exc:
        raise PolicyParseError(f"Invalid YAML: {exc}") from exc
    try:
        return PolicyDocument.model_validate(raw)
    except ValidationError as exc:
        raise PolicyParseError(f"Invalid policy schema: {exc}") from exc


def _field_matches(event_value: Any, pattern: str) -> bool:
    return fnmatch(str(event_value), pattern)


def requires_approval(policy: PolicyDocument, event_fields: dict[str, Any]) -> bool:
    for rule in policy.rules:
        matched = all(
            field in event_fields and _field_matches(event_fields[field], pattern)
            for field, pattern in rule.match.items()
        )
        if matched:
            return rule.require_approval
    return False
