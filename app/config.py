"""Application configuration using environment variables."""

import os


# PostgreSQL
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://shortener_user:shortener_pass@postgres:5432/shortener_db",
)
DB_HOST: str = os.getenv("DB_HOST", "postgres")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_NAME: str = os.getenv("DB_NAME", "shortener_db")
DB_USER: str = os.getenv("DB_USER", "shortener_user")
DB_PASSWORD: str = os.getenv("DB_PASSWORD", "shortener_pass")

# Redis
REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
REDIS_URL: str = os.getenv("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/0")
CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # 1 hour

# App
APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT: int = int(os.getenv("APP_PORT", "8000"))
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
SHORT_CODE_LENGTH: int = int(os.getenv("SHORT_CODE_LENGTH", "6"))
