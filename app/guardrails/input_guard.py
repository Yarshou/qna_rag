import re

from app.guardrails.exceptions import GuardrailViolationError

# Upper bound chosen to comfortably fit a real question while preventing
# context-flooding attacks that would saturate the model's context window.
_MAX_CONTENT_LENGTH = 4_000

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
    2. Injection patterns — a deny-list of well-known prompt-injection
       phrases caught before the model ever sees the message.

    Neither check attempts to reason about intent or domain; both operate
    on objective, measurable properties of the text.
    """

    def check(self, content: str) -> None:
        self._check_length(content)
        self._check_injection(content)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_length(self, content: str) -> None:
        if len(content) > _MAX_CONTENT_LENGTH:
            raise GuardrailViolationError(
                f"Message exceeds the maximum allowed length of {_MAX_CONTENT_LENGTH} characters."
            )

    def _check_injection(self, content: str) -> None:
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(content):
                raise GuardrailViolationError("Message contains a disallowed pattern.")
