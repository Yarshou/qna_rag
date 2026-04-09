__all__ = ["DatabaseError", "DatabaseConfigurationError"]


class DatabaseError(Exception):
    """Base exception for persistence-layer failures."""


class DatabaseConfigurationError(DatabaseError):
    """Raised when the database path is invalid or missing."""
