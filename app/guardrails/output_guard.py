import logging
import re

from app.config import settings
from app.guardrails.exceptions import GuardrailViolationError

logger = logging.getLogger(__name__)

# Patterns that should never appear in the *text* of a model response for
# this system.  Their presence means the model has leaked internal tool
# definitions — a reliable signal that role separation has broken down
# (e.g. a successful jailbreak or a model regression).
#
# We match only on function-call syntax (name immediately followed by '(')
# to avoid false positives when the user's *question* happens to mention
# these names and the model quotes them back.
_LEAKAGE_PATTERNS = [
    re.compile(r"\bsearch_knowledge_base\s*\(", re.IGNORECASE),
    re.compile(r"\bread_knowledge_file\s*\(", re.IGNORECASE),
]


class OutputGuard:
    """Validates assistant response content before it is persisted and returned.

    Design rationale
    ----------------
    Semantic grounding ("did the model actually use the KB?") cannot be
    reliably verified with code-based heuristics:

    * tool_calls_executed == 0 is not a violation — legitimate follow-up
      questions, proper topic-scope declines, and "I don't know" answers
      all produce 0 tool calls.
    * The model can execute tool calls and still hallucinate, so the count
      is not a proxy for answer quality either.
    * Any code-based grounding check requires a growing list of exceptions
      that can never be complete.

    Enforcement of grounding *behaviour* belongs in the system prompt, not
    in a post-hoc filter.  The output guard's job is limited to things that
    can be measured structurally and with near-zero false-positive rate:

    1. Maximum response length  — catches runaway generation.
       Configurable via MAX_OUTPUT_LENGTH (default: 8 000 chars).
    2. Internal leakage         — catches tool function-call syntax appearing
                                  in the response text, which reliably signals
                                  broken role separation.

    Observability
    -------------
    When tool_calls_executed == 0 for a non-trivial response the guard logs
    a warning.  This surfaces in structured logs without blocking valid
    responses, and provides the data needed to tune the system prompt over time.
    """

    def __init__(self, max_response_length: int | None = None) -> None:
        self._max_response_length = (
            max_response_length if max_response_length is not None else settings.MAX_OUTPUT_LENGTH
        )

    def check(self, content: str, tool_calls_executed: int = 0) -> str:
        self._check_length(content)
        self._check_leakage(content)
        self._warn_if_ungrounded(content, tool_calls_executed)
        return content

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_length(self, content: str) -> None:
        if len(content) > self._max_response_length:
            raise GuardrailViolationError(
                f"Assistant response exceeds the maximum allowed length of {self._max_response_length} characters."
            )

    def _check_leakage(self, content: str) -> None:
        for pattern in _LEAKAGE_PATTERNS:
            if pattern.search(content):
                raise GuardrailViolationError(
                    "Assistant response contains internal system details that must not be disclosed."
                )

    def _warn_if_ungrounded(self, content: str, tool_calls_executed: int) -> None:
        """Log a warning when the model answered without any KB access.

        This is a monitoring signal, not a hard gate.  A warning here means
        "investigate whether the system prompt is doing its job" — it does
        not mean the response is wrong.
        """
        if tool_calls_executed > 0:
            return

        # Short acknowledgements ("OK", "Got it", greetings) are not
        # substantive answers and do not require KB access.
        if len(content.strip()) < 80:
            return

        logger.warning(
            "output_guardrail_no_kb_usage",
            extra={"content_length": len(content)},
        )
