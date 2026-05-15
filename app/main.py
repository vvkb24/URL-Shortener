"""
URL Shortener — FastAPI Application

A real-world URL shortener (mini Bitly) demonstrating:
  • Day 1: Python project setup with proper tooling
  • Day 2: Dockerized FastAPI application
  • Day 3: PostgreSQL for persistent storage + Redis for caching
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from app.models import ShortenRequest, ShortenResponse, UrlStats, HealthResponse
from app.database import get_cursor, check_health as db_health
from app.cache import (
    cache_url,
    get_cached_url,
    increment_clicks,
    get_click_count,
    check_health as redis_health,
)
from app.utils import generate_short_code
from app.config import BASE_URL


# ── Startup / Shutdown ──────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run setup on startup and cleanup on shutdown."""
    # Startup: ensure the urls table exists
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                id          SERIAL PRIMARY KEY,
                short_code  VARCHAR(10) UNIQUE NOT NULL,
                original_url TEXT NOT NULL,
                click_count INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_short_code ON urls(short_code);
        """)
    print("✅ Database table ready")
    yield
    # Shutdown: nothing to clean up for now
    print("👋 Shutting down")


app = FastAPI(
    title="🔗 URL Shortener",
    description="A mini Bitly clone — Phase 0 learning project",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve static files (CSS, JS)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ── Frontend ───────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
def read_root():
    """Serve the frontend index.html."""
    try:
        with open("app/static/index.html") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Frontend not found")


# ── Health Check ────────────────────────────────────────────────


@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
def health_check() -> HealthResponse:
    """Check if PostgreSQL and Redis are reachable."""
    pg_ok = db_health()
    redis_ok = redis_health()
    status = "healthy" if (pg_ok and redis_ok) else "degraded"
    return HealthResponse(status=status, postgres=pg_ok, redis=redis_ok)


# ── Shorten URL ─────────────────────────────────────────────────


@app.post("/api/shorten", response_model=ShortenResponse, tags=["URLs"])
def shorten_url(body: ShortenRequest) -> ShortenResponse:
    """Create a shortened URL.

    1. Generate a unique short code (retry on collision)
    2. Store the mapping in PostgreSQL
    3. Pre-warm the Redis cache
    """
    original = str(body.url)

    # Generate unique short code (retry up to 5 times on collision)
    for _ in range(5):
        code = generate_short_code()
        try:
            with get_cursor() as cur:
                cur.execute(
                    "INSERT INTO urls (short_code, original_url) VALUES (%s, %s)",
                    (code, original),
                )
            break
        except Exception:
            continue
    else:
        raise HTTPException(status_code=500, detail="Could not generate unique code")

    # Pre-warm Redis cache so the first redirect is fast
    cache_url(code, original)

    return ShortenResponse(
        short_code=code,
        short_url=f"{BASE_URL}/{code}",
        original_url=original,
    )


# ── Redirect ────────────────────────────────────────────────────


@app.get("/{short_code}", tags=["Redirect"])
def redirect_to_url(short_code: str) -> RedirectResponse:
    """Redirect a short code to the original URL.

    Flow:
      1. Check Redis cache first (fast path)
      2. On cache miss → query PostgreSQL (slow path) → cache the result
      3. Increment click counter in Redis (async-friendly, batch flush later)
      4. Return 307 redirect
    """
    # 1. Try Redis cache first
    original_url = get_cached_url(short_code)

    if original_url:
        # Cache HIT — no database roundtrip needed
        increment_clicks(short_code)
        return RedirectResponse(url=original_url, status_code=307)

    # 2. Cache MISS — fall back to PostgreSQL
    with get_cursor() as cur:
        cur.execute(
            "SELECT original_url FROM urls WHERE short_code = %s",
            (short_code,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Short URL not found")

    original_url = row["original_url"]

    # 3. Cache the result for next time
    cache_url(short_code, original_url)
    increment_clicks(short_code)

    # 4. Update click count in PostgreSQL too
    with get_cursor() as cur:
        cur.execute(
            "UPDATE urls SET click_count = click_count + 1 WHERE short_code = %s",
            (short_code,),
        )

    return RedirectResponse(url=original_url, status_code=307)


# ── Stats ───────────────────────────────────────────────────────


@app.get("/api/stats/{short_code}", response_model=UrlStats, tags=["URLs"])
def get_stats(short_code: str) -> UrlStats:
    """Get statistics for a shortened URL.

    Combines the persisted click_count from PostgreSQL
    with any pending clicks still in Redis.
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT short_code, original_url, click_count, created_at "
            "FROM urls WHERE short_code = %s",
            (short_code,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Short URL not found")

    # Add any pending Redis clicks that haven't been flushed to DB yet
    redis_clicks = get_click_count(short_code)
    total_clicks = row["click_count"] + redis_clicks

    return UrlStats(
        short_code=row["short_code"],
        original_url=row["original_url"],
        click_count=total_clicks,
        created_at=row["created_at"],
        short_url=f"{BASE_URL}/{row['short_code']}",
    )


# ── List Recent URLs ────────────────────────────────────────────


@app.get("/api/recent", tags=["URLs"])
def list_recent_urls(limit: int = 10):
    """List the most recently shortened URLs."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT short_code, original_url, click_count, created_at "
            "FROM urls ORDER BY created_at DESC LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()

    return [
        {
            **row,
            "short_url": f"{BASE_URL}/{row['short_code']}",
        }
        for row in rows
    ]
