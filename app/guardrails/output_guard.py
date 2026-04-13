import logging

from app.guardrails.exceptions import GuardrailViolationError

logger = logging.getLogger(__name__)


class OutputGuard:
    """Validates assistant response content before it is persisted and returned."""

    def check(self, content: str, tool_calls_executed: int) -> str:
        self._check_grounding(content, tool_calls_executed)
        return content

    def _check_grounding(self, content: str, tool_calls_executed: int) -> None:
        if tool_calls_executed > 0:
            return

        # Phrases indicating the model properly acknowledged it could not answer
        # or declined an off-topic request — these are acceptable without KB usage.
        passthrough_phrases = (
            "i don't know",
            "i do not know",
            "i'm not sure",
            "i am not sure",
            "no information",
            "not in the knowledge base",
            "cannot find",
            "could not find",
            "outside the scope",
            "outside my knowledge",
            "not able to answer",
            "unable to answer",
        )
        content_lower = content.lower()
        if any(phrase in content_lower for phrase in passthrough_phrases):
            return

        logger.warning("output_guardrail_no_kb_usage", extra={"content_length": len(content)})
        raise GuardrailViolationError(
            "Assistant response was not grounded in the knowledge base."
        )
