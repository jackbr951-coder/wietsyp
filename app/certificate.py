"""Self-verifying product record: the QR URL carries signed data for offline checking."""
import base64
import hashlib
import hmac
import io
import json
import os
import secrets
from pathlib import Path

import segno


def _secret() -> bytes:
    value = os.getenv("DAFTER_SECRET", "").strip()
    if len(value) < 32 or value.lower() in {"change-me", "changeme"}:
        env_file = Path(__file__).resolve().parents[1] / ".env"
        value = secrets.token_urlsafe(48)
        try:
            with env_file.open("a", encoding="utf-8") as file:
                file.write(f"\nDAFTER_SECRET={value}\n")
        except OSError as exc:
            raise RuntimeError(
                f"Set DAFTER_SECRET to a random value of at least 32 characters in {env_file}"
            ) from exc
        os.environ["DAFTER_SECRET"] = value
    return value.encode()


def generate_secret() -> str:
    return secrets.token_urlsafe(32)


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(payload: dict) -> str:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True).encode()
    sig = hmac.new(_secret(), body, hashlib.sha256).digest()[:16]
    return f"{_b64(body)}.{_b64(sig)}"


def verify_token(token: str):
    """Returns (payload|None, valid: bool)."""
    try:
        b, s = token.split(".")
        body, sig = _unb64(b), _unb64(s)
        payload = json.loads(body)
    except Exception:
        return None, False
    good = hmac.new(_secret(), body, hashlib.sha256).digest()[:16]
    return payload, hmac.compare_digest(good, sig)


def base_url() -> str:
    return os.getenv("DAFTER_BASE_URL", "http://localhost:8000").rstrip("/")


def qr_svg(token: str, base: str | None = None) -> str:
    buf = io.BytesIO()
    segno.make(f"{(base or base_url()).rstrip('/')}/v/{token}", error="m").save(buf, kind="svg", scale=6, border=2, dark="#39261D")
    return buf.getvalue().decode()
