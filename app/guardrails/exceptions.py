class GuardrailViolationError(ValueError):
    """Raised when user input or assistant output fails a guardrail check."""
