"""Local secret storage.

Keys never leave the machine and are never returned to the renderer in clear.

If `cryptography` is installed we use Fernet (AES-128-CBC + HMAC). If not, we
fall back to a machine-scoped XOR obfuscation and mark the vault as
"obfuscated" so the UI can warn the user. Obfuscation is NOT encryption -- the
README says so explicitly. We never pretend otherwise.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import uuid

try:  # optional dependency
    from cryptography.fernet import Fernet, InvalidToken

    _HAVE_FERNET = True
except Exception:  # pragma: no cover - fallback path
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore
    _HAVE_FERNET = False

from .config import HOME_DIR

_KEY_FILE = HOME_DIR / "vault.key"


def _machine_seed() -> bytes:
    raw = "|".join(
        [
            platform.node() or "",
            os.environ.get("USERNAME") or os.environ.get("USER") or "",
            str(uuid.getnode()),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _load_key() -> bytes:
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()
    key = _machine_seed() if not _HAVE_FERNET else Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    try:
        os.chmod(_KEY_FILE, 0o600)
    except OSError:
        pass
    return key


def vault_backend() -> str:
    return "fernet" if _HAVE_FERNET else "obfuscated"


def _xor(data: bytes, key: bytes) -> bytes:
    stream = hashlib.sha256(key + b"|aitrader-vault").digest()
    out = bytearray()
    for i, b in enumerate(data):
        out.append(b ^ stream[i % len(stream)])
    return bytes(out)


def encrypt(value: str | None) -> str:
    if not value:
        return ""
    key = _load_key()
    if _HAVE_FERNET:
        return "f1:" + Fernet(key).encrypt(value.encode("utf-8")).decode("ascii")
    payload = base64.urlsafe_b64encode(_xor(value.encode("utf-8"), key)).decode("ascii")
    return "x1:" + payload


def decrypt(value: str | None) -> str:
    if not value:
        return ""
    key = _load_key()
    if value.startswith("f1:"):
        if not _HAVE_FERNET:
            return ""
        try:
            return Fernet(key).decrypt(value[3:].encode("ascii")).decode("utf-8")
        except InvalidToken:
            return ""
    if value.startswith("x1:"):
        try:
            return _xor(base64.urlsafe_b64decode(value[3:]), key).decode("utf-8")
        except Exception:
            return ""
    return value


def mask(secret: str | None, keep: int = 4) -> str:
    if not secret:
        return ""
    if len(secret) <= keep:
        return "*" * len(secret)
    return "*" * (len(secret) - keep) + secret[-keep:]


def encrypt_json(obj: dict) -> str:
    return encrypt(json.dumps(obj)) if obj else ""


def decrypt_json(value: str | None) -> dict:
    raw = decrypt(value)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def stable_hash(text: str) -> str:
    return hmac.new(_load_key(), text.encode("utf-8"), hashlib.sha256).hexdigest()
