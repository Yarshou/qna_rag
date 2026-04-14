"""Shared base model for all API request and response schemas.

Every schema in this package inherits from :class:`BaseSchema` to ensure a
consistent Pydantic configuration across the entire API surface.  The key
setting is ``extra="forbid"``, which causes validation to reject payloads
that contain unexpected fields — a defensive measure against accidental data
leakage and client contract drift.
"""

from pydantic import BaseModel, ConfigDict


class BaseSchema(BaseModel):
    """Pydantic base model with shared configuration for all API schemas.

    Configuration
    -------------
    extra = "forbid"
        Unknown fields in incoming payloads raise a ``ValidationError``
        rather than being silently ignored.  This enforces strict API
        contracts on both requests and responses.
    """

    model_config = ConfigDict(extra="forbid")
