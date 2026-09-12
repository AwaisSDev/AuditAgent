"""PII redaction — the primary pass, using Microsoft Presidio.

Runs inside the arq worker (not the SDK, not the request handler) because
Presidio's NER pipeline is too slow for the ingest endpoint's response time
and far too slow for the SDK's <5ms in-process overhead budget. See
worker/tasks.py for where this fits in the pipeline.
"""

from functools import lru_cache
from typing import Any

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# Explicit small model, not Presidio's implicit default (en_core_web_lg,
# ~600MB) — noticeably faster to download/load in the worker's Docker image
# and at runtime, for a modest, acceptable hit to NER recall on an MVP budget.
_NLP_CONFIGURATION = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
}

ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "US_BANK_NUMBER",
    "IBAN_CODE",
    "IP_ADDRESS",
    "LOCATION",
    "CRYPTO",
    "US_PASSPORT",
    "US_DRIVER_LICENSE",
    "MEDICAL_LICENSE",
]


@lru_cache
def _analyzer() -> AnalyzerEngine:
    nlp_engine = NlpEngineProvider(nlp_configuration=_NLP_CONFIGURATION).create_engine()
    return AnalyzerEngine(nlp_engine=nlp_engine)


@lru_cache
def _anonymizer() -> AnonymizerEngine:
    return AnonymizerEngine()


def _redact_text(text: str) -> str:
    if not text or not text.strip():
        return text
    results = _analyzer().analyze(text=text, entities=ENTITIES, language="en")
    if not results:
        return text
    anonymized = _anonymizer().anonymize(
        text=text,
        analyzer_results=results,
        operators={"DEFAULT": OperatorConfig("replace", {"new_value": "[REDACTED]"})},
    )
    return anonymized.text


def redact_pii(value: Any) -> Any:
    """Recursively redacts PII from strings anywhere inside a JSON-like value."""
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {k: redact_pii(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_pii(v) for v in value]
    return value
