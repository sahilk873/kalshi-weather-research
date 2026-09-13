"""Kalshi RSA access-key authentication helpers.

This module only creates request headers. It does not submit orders or mutate
an account. Private key material is never returned in diagnostics.
"""
from __future__ import annotations

import base64
import re
import time
from pathlib import Path


def parse_credential_file(path: Path) -> tuple[str, str]:
    """Return ``(api_key_id, private_key_pem)`` from a local credential file."""
    text = path.read_text()
    match = re.search(r"-----BEGIN RSA PRIVATE KEY-----.*?-----END RSA PRIVATE KEY-----", text, re.DOTALL)
    if not match:
        match = re.search(r"-----BEGIN PRIVATE KEY-----.*?-----END PRIVATE KEY-----", text, re.DOTALL)
    key_match = re.search(r"^\s*API\s+KEY\s+ID\s*:\s*(\S+)\s*$", text, re.MULTILINE | re.IGNORECASE)
    if not match or not key_match:
        raise ValueError("credential file must contain a PEM private key and API KEY ID")
    return key_match.group(1), match.group(0) + "\n"


def sign_access_request(api_key_id: str, private_key_pem: str, *, method: str = "GET",
                        path: str = "/trade-api/ws/v2", timestamp_ms: int | None = None) -> dict[str, str]:
    """Build Kalshi RSA-PSS/SHA-256 access headers for one request."""
    if not api_key_id or not private_key_pem:
        raise ValueError("API key ID and private key are required")
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("cryptography is required for RSA access-key authentication") from exc
    ts = int(time.time() * 1000) if timestamp_ms is None else int(timestamp_ms)
    message = f"{ts}{method.upper()}{path}".encode("utf-8")
    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    signature = key.sign(message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    return {"KALSHI-ACCESS-KEY": api_key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii"),
            "KALSHI-ACCESS-TIMESTAMP": str(ts)}
