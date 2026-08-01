"""Shared, domain-agnostic platform primitives."""

from healthos_platform.config import BaseServiceSettings, Environment
from healthos_platform.models import ErrorDetail, ErrorResponse, HealthResponse

__all__ = [
    "BaseServiceSettings",
    "Environment",
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
]
