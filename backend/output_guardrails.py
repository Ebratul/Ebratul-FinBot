import re
from typing import Any, Dict, List, Optional

from guardrails import Guard
from guardrails.validator_base import (
    FailResult,
    OnFailAction,
    PassResult,
    ValidationResult,
    Validator,
    register_validator,
)


# ── 1. SOURCE CITATION VALIDATOR ──────────────────────────────────────────────

@register_validator(name="finbot/source-citation", data_type="string")
class SourceCitationValidator(Validator):
    _CITATION_REGEX = re.compile(
        r"\bsource[:\s]|\bpage\s*\d+|\bp\.\s*\d+|\[page\s*\d+\]|\(p\.\s*\d+\)",
        re.IGNORECASE,
    )
    _WARNING = (
        "\n\n⚠️ **Source Warning:** This response does not cite a specific source document "
        "or page number. Please verify the information independently."
    )

    def validate(self, value: str, metadata: Dict[str, Any]) -> ValidationResult:
        if self._CITATION_REGEX.search(value):
            return PassResult()
        return FailResult(
            error_message="Response does not cite any source document or page number.",
            fix_value=value + self._WARNING,
        )


# ── 2. GROUNDING VALIDATOR ────────────────────────────────────────────────────

@register_validator(name="finbot/grounding-check", data_type="string")
class GroundingValidator(Validator):
    _FINANCIAL_REGEX = re.compile(
        r"[\$₹€£]\s?\d[\d,\.]+|"   # Currency values: $1.2M, ₹50,000
        r"\b\d[\d,\.]+\s?%|"        # Percentages: 3.5%, 12%
        r"\bQ[1-4]\s?\d{4}\b|"      # Quarter references: Q3 2024
        r"\bFY\s?\d{4}\b|"          # Fiscal year: FY2024
        r"\b\d{4}[-/]\d{2}[-/]\d{2}\b",  # ISO dates: 2024-01-15
        re.IGNORECASE,
    )
    _DISCLAIMER = (
        "\n\n⚠️ **Grounding Warning:** This response contains financial figures or dates "
        "that could not be fully verified against the retrieved source documents. "
        "Please cross-check with the original documents before acting on this information."
    )

    def validate(self, value: str, metadata: Dict[str, Any]) -> ValidationResult:
        retrieved_chunks: List[str] = metadata.get("retrieved_chunks", [])
        figures = self._FINANCIAL_REGEX.findall(value)

        if not figures:
            return PassResult()

        all_chunk_text = " ".join(retrieved_chunks)
        for figure in figures:
            if figure.strip() not in all_chunk_text:
                return FailResult(
                    error_message=f"Figure '{figure}' not traceable to any retrieved chunk.",
                    fix_value=value + self._DISCLAIMER,
                )

        return PassResult()


# ── 3. CROSS-ROLE LEAKAGE VALIDATOR ──────────────────────────────────────────

_COLLECTION_LEAK_SIGNALS: Dict[str, List[str]] = {
    "finance": [
        "budget", "revenue", "profit", "loss", "earnings", "financial projection",
        "investor", "quarterly report", "fiscal year", "EBITDA", "net income",
    ],
    "engineering": [
        "API reference", "microservice", "deployment", "docker", "kubernetes",
        "incident report", "SLA", "runbook", "pull request", "system architecture",
    ],
    "marketing": [
        "campaign performance", "brand guidelines", "market share", "competitor analysis",
        "customer acquisition", "go-to-market", "social media campaign",
    ],
}

_ROLE_AUTHORIZED_COLLECTIONS: Dict[str, set] = {
    "employee":    {"general"},
    "finance":     {"general", "finance"},
    "engineering": {"general", "engineering"},
    "marketing":   {"general", "marketing"},
    "c_level":     {"general", "finance", "engineering", "marketing"},
}

_LEAKAGE_WARNING = (
    "\n\n🔒 **Security Notice:** This response may reference content from a document "
    "collection outside your authorized access. Please contact your administrator "
    "if you believe this is an error."
)


@register_validator(name="finbot/cross-role-leakage", data_type="string")
class CrossRoleLeakageValidator(Validator):
    def validate(self, value: str, metadata: Dict[str, Any]) -> ValidationResult:
        user_role: str = metadata.get("user_role", "employee")
        authorized = _ROLE_AUTHORIZED_COLLECTIONS.get(user_role, {"general"})
        response_lower = value.lower()

        for collection, signals in _COLLECTION_LEAK_SIGNALS.items():
            if collection in authorized:
                continue
            for signal in signals:
                if signal.lower() in response_lower:
                    return FailResult(
                        error_message=(
                            f"Response contains '{signal}' which signals unauthorized "
                            f"access to the '{collection}' collection."
                        ),
                        fix_value=value + _LEAKAGE_WARNING,
                    )

        return PassResult()


class OutputGuardrails:
    def __init__(self):
        self.output_guard = (
            Guard()
            .use(SourceCitationValidator(on_fail=OnFailAction.FIX))
            .use(GroundingValidator(on_fail=OnFailAction.FIX))
            .use(CrossRoleLeakageValidator(on_fail=OnFailAction.EXCEPTION))
        )

    def run_output_guardrails(
        self,
        response: str,
        user_role: str,
        retrieved_chunks: List[str],
    ) -> str:
        try:
            outcome = self.output_guard.validate(
                response,
                metadata={
                    "retrieved_chunks": retrieved_chunks,
                    "user_role": user_role,
                },
            )
            return outcome.validated_output or response

        except Exception as e:
            print(f"[OutputGuardrail] Cross-role leakage blocked: {e}")
            return (
                "🔒 **Access Denied:** This response has been blocked because it may contain "
                "information from document collections you are not authorized to access. "
                "Please rephrase your question or contact your administrator."
            )
