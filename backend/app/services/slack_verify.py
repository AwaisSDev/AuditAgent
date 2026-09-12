from slack_sdk.signature import SignatureVerifier

from app.config import get_settings


def verify_slack_request(body: bytes, timestamp: str, signature: str) -> bool:
    settings = get_settings()
    if not settings.slack_signing_secret:
        return False
    verifier = SignatureVerifier(settings.slack_signing_secret)
    return verifier.is_valid(body=body, timestamp=timestamp, signature=signature)
