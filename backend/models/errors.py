"""Schema for error responses."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
