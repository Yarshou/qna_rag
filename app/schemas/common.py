from typing import Literal

from app.schemas.base import BaseSchema


class ErrorDetail(BaseSchema):
    code: str
    message: str


class ErrorResponse(BaseSchema):
    error: ErrorDetail


class StatusResponse(BaseSchema):
    status: Literal["ok"]
