"""PostgreSQL database connection and operations using psycopg2."""

import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Generator, Any

from app.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


def get_connection() -> psycopg2.extensions.connection:
    """Create a new database connection."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


@contextmanager
def get_cursor() -> Generator[Any, None, None]:
    """Context manager that provides a database cursor with auto-commit.

    Usage:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM urls")
            rows = cur.fetchall()
    """
    conn = get_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def check_health() -> bool:
    """Check if PostgreSQL is reachable."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return True
    except Exception:
        return False
