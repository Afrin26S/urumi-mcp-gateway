import asyncio
import ipaddress
import os
import re
import socket
import sqlite3
import time
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

import config  # noqa: F401
import db
import security
import upstream
import agent

api = FastAPI(title="MCP Gateway API")
COOKIE_SECURE = os.getenv("GATEWAY_COOKIE_SECURE", "false").lower() == "true"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")


# ---------- auth ----------
def session_user(request: Request) -> dict:
    token = request.cookies.get("session")
    user_id = security.read_session(token) if token else None
    user = db.one("SELECT id, email, name, role, disabled FROM users WHERE id = ?", (user_id,)) if user_id else None
    if not user or user["disabled"]:
        raise HTTPException(401, "Not signed in")
    return user


def admin_only(user: dict = Depends(session_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(403, "Admins only")
    return user


def public_user(u: dict) -> dict:
    return {k: u[k] for k in ("id", "email", "name", "role")}


_failures: dict[str, list[float]] = {}
MAX_FAILURES, FAILURE_WINDOW = 5, 600
class Login(BaseModel):
    email: str
    password: str


@api.get("/health")
def health():
    return {"status": "ok"}


@api.post("/auth/login")
def login(body: Login, response: Response):
    key = body.email.strip().lower()
    now = time.time()
    recent = [t for t in _failures.get(key, []) if now - t < FAILURE_WINDOW]
    if len(recent) >= MAX_FAILURES:
        raise HTTPException(429, "Too many failed sign-in attempts. Try again in 10 minutes.")
    user = db.one("SELECT * FROM users WHERE email = ?", (key,))
    if not user or user["disabled"] or not security.verify_password(user["password_hash"], body.password):
        if len(_failures) > 5000:
            _failures.clear()  # bound the memory an attacker can use
        _failures[key] = [*recent, now]
        raise HTTPException(401, "Wrong email or password")
    _failures.pop(key, None)
    response.set_cookie("session", security.make_session(user["id"]), httponly=True,
                        samesite="lax", secure=COOKIE_SECURE, max_age=security.SESSION_SECONDS)
    return public_user(user)


@api.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie("session")
    return {"ok": True}


@api.get("/me")
def me(user: dict = Depends(session_user)):
    return public_user(user)


# ---------- users (admin) ----------
class NewUser(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(min_length=1, max_length=80)
    role: Literal["admin", "member"] = "member"
    password: str = Field(min_length=10, max_length=128)


class UserPatch(BaseModel):
    disabled: bool


@api.post("/users", status_code=201)
def create_user(body: NewUser, _: dict = Depends(admin_only)):
    try:
        new_id = db.execute(
            "INSERT INTO users(email, name, role, password_hash, created_at) VALUES (?,?,?,?,?)",
            (body.email.lower(), body.name, body.role, security.hash_password(body.password), db.now()),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "A user with that email already exists")
    return {"id": new_id, "email": body.email.lower(), "name": body.name, "role": body.role}


@api.get("/users")
def list_users(_: dict = Depends(admin_only)):
    return db.query("SELECT id, email, name, role, disabled, created_at FROM users ORDER BY id")


@api.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch, admin: dict = Depends(admin_only)):
    if user_id == admin["id"] and body.disabled:
        raise HTTPException(400, "You cannot disable yourself")
    db.execute("UPDATE users SET disabled = ? WHERE id = ?", (int(body.disabled), user_id))
    return {"ok": True}


# ---------- API keys ----------
class NewKey(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    user_id: int | None = None  # admins may issue a key for someone else


@api.post("/keys", status_code=201)
def create_key(body: NewKey, user: dict = Depends(session_user)):
    owner_id = body.user_id or user["id"]
    if owner_id != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "Only admins can issue keys for other users")
    if not db.one("SELECT 1 AS x FROM users WHERE id = ? AND disabled = 0", (owner_id,)):
        raise HTTPException(404, "No such active user")
    full, prefix, digest = security.new_api_key()
    key_id = db.execute(
        "INSERT INTO api_keys(user_id, name, prefix, key_hash, created_at) VALUES (?,?,?,?,?)",
        (owner_id, body.name, prefix, digest, db.now()),
    )
    return {"id": key_id, "name": body.name, "prefix": prefix, "key": full,
            "warning": "Copy this key now. It is shown only once."}


@api.get("/keys")
def list_keys(user: dict = Depends(session_user)):
    sql = ("SELECT k.id, k.name, k.prefix, k.created_at, k.last_used_at, k.revoked_at, u.email AS owner "
           "FROM api_keys k JOIN users u ON u.id = k.user_id")
    if user["role"] == "admin":
        return db.query(sql + " ORDER BY k.id DESC")
    return db.query(sql + " WHERE k.user_id = ? ORDER BY k.id DESC", (user["id"],))


@api.delete("/keys/{key_id}")
def revoke_key(key_id: int, user: dict = Depends(session_user)):
    row = db.one("SELECT user_id FROM api_keys WHERE id = ?", (key_id,))
    if not row or (row["user_id"] != user["id"] and user["role"] != "admin"):
        raise HTTPException(404, "No such key")  # 404, not 403: don't reveal that other people's keys exist
    db.execute("UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL", (db.now(), key_id))
    return {"ok": True}


# ---------- upstream servers ----------
AuthType = Literal["none", "bearer", "header"]


def _check_auth(auth_type: str, header_name: str | None, credential: str | None) -> None:
    if auth_type != "none" and not credential:
        raise HTTPException(422, "A credential is required when auth_type is not 'none'")
    if auth_type == "header" and not header_name:
        raise HTTPException(422, "header_name is required when auth_type is 'header'")


def _check_url(url: str) -> None:
    if not url.startswith(("http://", "https://")):
        raise HTTPException(422, "url must start with http:// or https://")
    host = urlparse(url).hostname
    if not host:
        raise HTTPException(422, "url has no host")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return  # does not resolve (yet): it will simply show as unreachable
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
            raise HTTPException(422, "That address is not allowed (loopback, link-local such as cloud metadata, or reserved)")


class NewServer(BaseModel):
    slug: str
    name: str = Field(min_length=1, max_length=80)
    url: str
    auth_type: AuthType = "none"
    header_name: str | None = None
    credential: str | None = None

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not SLUG_RE.match(v):
            raise ValueError("slug: 1-24 characters, lowercase letters, digits and hyphens")
        return v


class ServerPatch(BaseModel):
    name: str | None = None
    url: str | None = None
    enabled: bool | None = None
    auth_type: AuthType | None = None
    header_name: str | None = None
    credential: str | None = None


def server_view(row: dict, state: dict, user: dict) -> dict:
    return {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "url": row["url"],
        "auth_type": row["auth_type"],
        "header_name": row["header_name"],
        "has_credential": bool(row["credential_enc"]),
        "enabled": bool(row["enabled"]),
        "status": state["status"],
        "error": state["error"],
        "tools": [
            {
                "name": f"{row['slug']}__{t.name}",
                "description": t.description,
            }
            for t in state["tools"]
            if upstream.allowed(user, f"{row['slug']}__{t.name}")
        ],
    }


@api.get("/servers")
async def list_servers(user: dict = Depends(session_user)):
    rows = await asyncio.to_thread(db.query, "SELECT * FROM servers ORDER BY slug")
    states = await upstream.status_for(rows)
    return [server_view(r, states[r["slug"]], user) for r in rows]


@api.post("/servers", status_code=201)
def create_server(body: NewServer, _: dict = Depends(admin_only)):
    _check_url(body.url)
    _check_auth(body.auth_type, body.header_name, body.credential)
    try:
        new_id = db.execute(
            "INSERT INTO servers(slug, name, url, auth_type, header_name, credential_enc, created_at) VALUES (?,?,?,?,?,?,?)",
            (body.slug, body.name, body.url, body.auth_type, body.header_name,
             security.encrypt(body.credential) if body.credential else None, db.now()),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "That slug is already in use")
    return {"id": new_id, "slug": body.slug}


@api.patch("/servers/{server_id}")
def patch_server(server_id: int, body: ServerPatch, _: dict = Depends(admin_only)):
    row = db.one("SELECT * FROM servers WHERE id = ?", (server_id,))
    if not row:
        raise HTTPException(404, "No such server")
    changes = body.model_dump(exclude_unset=True)
    if "url" in changes:
        _check_url(changes["url"])
    if "credential" in changes:
        cred = changes.pop("credential")
        changes["credential_enc"] = security.encrypt(cred) if cred else None
    if "enabled" in changes:
        changes["enabled"] = int(changes["enabled"])
    allowed = {"name", "url", "enabled", "auth_type", "header_name", "credential_enc"}
    changes = {k: v for k, v in changes.items() if k in allowed}  # column names come from this fixed list only
    if changes:
        sets = ", ".join(f"{k} = ?" for k in changes)
        db.execute(f"UPDATE servers SET {sets} WHERE id = ?", (*changes.values(), server_id))
    upstream.forget(row["slug"])
    return {"ok": True}


@api.delete("/servers/{server_id}")
def delete_server(server_id: int, _: dict = Depends(admin_only)):
    row = db.one("SELECT slug FROM servers WHERE id = ?", (server_id,))
    if not row:
        raise HTTPException(404, "No such server")
    db.execute("DELETE FROM servers WHERE id = ?", (server_id,))
    upstream.forget(row["slug"])
    return {"ok": True}


# ---------- audit log (admin) ----------
@api.get("/audit")
def audit(limit: int = 100, _: dict = Depends(admin_only)):
    return db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (min(max(limit, 1), 500),))


# ---------- chat agent ----------
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]  # the browser may NOT send system or tool messages
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)


@api.post("/chat")
async def chat(body: ChatRequest, user: dict = Depends(session_user)):
    if body.messages[-1].role != "user":
        raise HTTPException(422, "The last message must come from the user")
    try:
        return await agent.run_chat(user, [m.model_dump() for m in body.messages])
    except agent.ChatNotConfigured:
        raise HTTPException(503, "Chat is not configured on this server")
    except agent.LlmError as exc:
        raise HTTPException(502, f"The language model request failed ({exc})")