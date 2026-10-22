import hashlib
import hmac
import os
import secrets
import time

import jwt
from argon2 import PasswordHasher
from cryptography.fernet import Fernet

import config  # noqa: F401
import db

_hasher = PasswordHasher()
_fernet = Fernet(os.environ["GATEWAY_ENCRYPTION_KEY"].encode())
_JWT_SECRET = os.environ["GATEWAY_JWT_SECRET"]
KEY_PREFIX = "umk"
SESSION_SECONDS = 8 * 3600


# ---- passwords (dashboard login): slow on purpose ----
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return _hasher.verify(stored, password)
    except Exception:
        return False


# ---- API keys (MCP clients): random 256-bit secrets, checked on every request ----
def hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


def new_api_key() -> tuple[str, str, str]:
    prefix = secrets.token_hex(4)
    full = f"{KEY_PREFIX}_{prefix}_{secrets.token_urlsafe(32)}"
    return full, prefix, hash_key(full)  # the full key is shown to the user once, then forgotten


def authenticate_api_key(full_key: str) -> dict | None:
    parts = full_key.split("_", 2)
    if len(parts) != 3 or parts[0] != KEY_PREFIX:
        return None
    row = db.one(
        "SELECT k.id AS key_id, k.key_hash, k.revoked_at, u.id, u.email, u.role, u.disabled "
        "FROM api_keys k JOIN users u ON u.id = k.user_id WHERE k.prefix = ?",
        (parts[1],),
    )
    if not row or row["revoked_at"] or row["disabled"]:
        return None
    if not hmac.compare_digest(row["key_hash"], hash_key(full_key)):  # constant-time comparison
        return None
    db.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (db.now(), row["key_id"]))
    return {"id": row["id"], "email": row["email"], "role": row["role"], "key_id": row["key_id"]}


# ---- upstream credentials: encrypted at rest ----
def encrypt(plain: str) -> str:
    return _fernet.encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet.decrypt(token.encode()).decode()


# ---- dashboard session cookie ----
def make_session(user_id: int) -> str:
    claims = {"sub": str(user_id), "exp": int(time.time()) + SESSION_SECONDS}
    return jwt.encode(claims, _JWT_SECRET, algorithm="HS256")


def read_session(token: str) -> int | None:
    try:
        return int(jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])["sub"])
    except Exception:
        return None