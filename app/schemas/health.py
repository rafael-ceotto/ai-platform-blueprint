"""Schemas for health/readiness endpoints."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app_name: str
    version: str
    environment: str


class DependencyStatus(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: list[DependencyStatus]
