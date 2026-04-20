import re

from app.config import settings
from app.guardrails.exceptions import GuardrailViolationError

# Well-known prompt-injection patterns.  These are structurally distinctive
# enough that they almost never appear in legitimate questions, so the
# false-positive risk is negligible.  We check *before* the message reaches
# the LLM, which is the only reliable place to act on them.
_INJECTION_PATTERNS = [
    # Classic override phrase
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    # "system:" only at the very start of a line (not mid-sentence like "the system: …")
    re.compile(r"(^|\n)\s*system\s*:", re.IGNORECASE),
    # XML / HTML system tag used in some prompt formats
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    # Llama-style instruction delimiter
    re.compile(r"\[INST\]", re.IGNORECASE),
    # Persona hijack: "you are now a/an …"
    re.compile(r"you\s+are\s+now\s+(a|an)\b", re.IGNORECASE),
    # Explicit instruction cancellation
    re.compile(r"disregard\s+(your\s+)?instructions", re.IGNORECASE),
]


class InputGuard:
    """Validates user message content before it is sent to the LLM.

    Two checks are applied, in order of cheapness:
    1. Length — a hard structural limit that prevents context flooding.
       Configurable via MAX_INPUT_LENGTH (default: 4 000 chars).
    2. Injection patterns — a deny-list of well-known prompt-injection
       phrases caught before the model ever sees the message.

    Neither check attempts to reason about intent or common_types; both operate
    on objective, measurable properties of the text.
    """

    def __init__(self, max_content_length: int | None = None) -> None:
        self._max_content_length = max_content_length if max_content_length is not None else settings.MAX_INPUT_LENGTH

    def check(self, content: str) -> None:
        self._check_length(content)
        self._check_injection(content)

    def _check_length(self, content: str) -> None:
        if len(content) > self._max_content_length:
            raise GuardrailViolationError(
                f"Message exceeds the maximum allowed length of {self._max_content_length} characters."
            )

    def _check_injection(self, content: str) -> None:
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(content):
                raise GuardrailViolationError("Message contains a disallowed pattern.")
