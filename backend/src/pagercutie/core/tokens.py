"""Opaque bearer tokens (session cookies, source ingest tokens); only their hash is stored (ADR-0031)."""

import hashlib
import secrets


def new_token() -> str:
    """A random URL-safe token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> bytes:
    """SHA-256 of a token, 32 bytes."""
    return hashlib.sha256(token.encode()).digest()
