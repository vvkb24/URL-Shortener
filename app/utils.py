"""Utility functions for URL shortening."""

import string
import random

from app.config import SHORT_CODE_LENGTH

# Base62 alphabet: a-z, A-Z, 0-9
ALPHABET = string.ascii_letters + string.digits


def generate_short_code(length: int = SHORT_CODE_LENGTH) -> str:
    """Generate a random base62 short code.

    With 6 characters and 62 possible chars per position,
    there are 62^6 = ~56.8 billion possible codes.
    Collision probability is negligible for small-scale usage.

    Args:
        length: Number of characters in the short code.

    Returns:
        A random alphanumeric string like 'aB3xZ9'.
    """
    return "".join(random.choices(ALPHABET, k=length))
