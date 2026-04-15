from __future__ import annotations

import hashlib
import hmac


def build_signature(*, body: bytes, timestamp: str, secret: str) -> str:
    payload = timestamp.encode() + b"." + body
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
