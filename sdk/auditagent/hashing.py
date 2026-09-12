import hashlib
import json
from typing import Any


def hash_prompt(inputs: dict[str, Any]) -> str:
    """Hashes whatever looks like the actual model prompt (a `prompt` or
    `messages` kwarg) so evidence packs can reference 'this exact prompt ran'
    without storing the prompt text itself. Falls back to hashing all inputs
    if neither key is present."""
    payload = inputs.get("prompt") or inputs.get("messages") or inputs
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
