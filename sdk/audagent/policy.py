"""Client-side policy evaluation (F2: "SDK reads policy on init").

This intentionally mirrors backend/app/services/policy_engine.py — small
enough (~30 lines) that duplicating it beats adding a shared package
dependency between two independently-deployed pieces (SDK ships to PyPI,
backend ships to Railway) for an MVP.
"""

from fnmatch import fnmatch
from typing import Any

import yaml

DEFAULT_POLICY_YAML = """\
rules:
  - match:
      action_type: external
    require_approval: true
"""


class Policy:
    def __init__(self, rules_yaml: str):
        parsed = yaml.safe_load(rules_yaml) or {}
        self.rules: list[dict] = parsed.get("rules", [])

    def requires_approval(self, action_type: str, action_name: str) -> bool:
        fields = {"action_type": action_type, "action_name": action_name}
        for rule in self.rules:
            match: dict[str, str] = rule.get("match", {})
            if all(field in fields and fnmatch(str(fields[field]), pattern) for field, pattern in match.items()):
                return bool(rule.get("require_approval", True))
        return False

    @classmethod
    def default(cls) -> "Policy":
        return cls(DEFAULT_POLICY_YAML)
