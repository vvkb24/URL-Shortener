"""Pydantic models for request/response validation."""

from pydantic import BaseModel, HttpUrl
from datetime import datetime


# ── Request Models ──────────────────────────────────────────────

class ShortenRequest(BaseModel):
    """Request body for creating a short URL."""
    url: HttpUrl  # Validates that it's a proper HTTP/HTTPS URL


# ── Response Models ─────────────────────────────────────────────

class ShortenResponse(BaseModel):
    """Response after creating a short URL."""
    short_code: str
    short_url: str
    original_url: str


class UrlStats(BaseModel):
    """Statistics for a shortened URL."""
    short_code: str
    original_url: str
    click_count: int
    created_at: datetime
    short_url: str


class HealthResponse(BaseModel):
    """Health check response showing service statuses."""
    status: str
    postgres: bool
    redis: bool
