import re

from app.guardrails.exceptions import GuardrailViolationError

_MAX_CONTENT_LENGTH = 4_000

_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"\bsystem\s*:", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an)\s+\w", re.IGNORECASE),
    re.compile(r"disregard\s+(your\s+)?instructions", re.IGNORECASE),
]


class InputGuard:
    """Validates user message content before it is sent to the LLM."""

    def check(self, content: str) -> None:
        self._check_length(content)
        self._check_injection(content)

    def _check_length(self, content: str) -> None:
        if len(content) > _MAX_CONTENT_LENGTH:
            raise GuardrailViolationError(
                f"Message exceeds maximum allowed length of {_MAX_CONTENT_LENGTH} characters."
            )

    def _check_injection(self, content: str) -> None:
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(content):
                raise GuardrailViolationError("Message contains a disallowed pattern.")
