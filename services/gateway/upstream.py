import asyncio
import os
import time
from contextlib import asynccontextmanager

import anyio
import httpx2
from mcp import Client, MCPError
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent, Tool

import config  # noqa: F401
import db
import security

LIST_TIMEOUT = float(os.getenv("GATEWAY_LIST_TIMEOUT", "5"))
CALL_TIMEOUT = float(os.getenv("GATEWAY_CALL_TIMEOUT", "10"))
CACHE_TTL = float(os.getenv("GATEWAY_CACHE_TTL", "10"))
_state: dict[str, dict] = {}  # slug -> {"status", "error", "tools", "checked_at"}


def _describe(exc: BaseException) -> str:
    while getattr(exc, "exceptions", None):  # unwrap ExceptionGroup to the real cause
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"[:200]


def _error(text: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


@asynccontextmanager
async def _connect(server: dict):
    headers: dict[str, str] = {}
    if server["credential_enc"]:
        secret = security.decrypt(server["credential_enc"])  # decrypted only here, in memory
        if server["auth_type"] == "bearer":
            headers["Authorization"] = f"Bearer {secret}"
        elif server["auth_type"] == "header":
            headers[server["header_name"]] = secret
    async with httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(CALL_TIMEOUT)) as http:
        async with Client(streamable_http_client(server["url"], http_client=http)) as client:
            yield client


async def _refresh(server: dict) -> dict:
    """Ask one upstream for its tools. Never raises: failures become status 'unreachable'."""
    try:
        with anyio.fail_after(LIST_TIMEOUT):
            async with _connect(server) as client:
                tools: list[Tool] = []
                cursor = None
                for _ in range(10):  # follow pagination, with an upper bound
                    page = await client.list_tools(cursor=cursor)
                    tools.extend(page.tools)
                    cursor = page.next_cursor
                    if cursor is None:
                        break
        state = {"status": "connected", "error": None, "tools": tools}
    except TimeoutError:
        state = {"status": "unreachable", "error": f"no answer within {LIST_TIMEOUT:g} s", "tools": []}
    except Exception as exc:
        state = {"status": "unreachable", "error": _describe(exc), "tools": []}
    state["checked_at"] = time.monotonic()
    _state[server["slug"]] = state
    return state


async def _ensure_fresh(servers: list[dict]) -> None:
    cutoff = time.monotonic() - CACHE_TTL
    stale = [s for s in servers if s["enabled"] and _state.get(s["slug"], {}).get("checked_at", -1e9) < cutoff]
    await asyncio.gather(*(_refresh(s) for s in stale))  # all stale servers in parallel


def forget(slug: str) -> None:
    _state.pop(slug, None)  # called when an admin edits, disables or deletes a server


async def status_for(servers: list[dict]) -> dict[str, dict]:
    await _ensure_fresh(servers)
    out = {}
    for s in servers:
        if not s["enabled"]:
            out[s["slug"]] = {"status": "disabled", "error": None, "tools": []}
        else:
            out[s["slug"]] = _state.get(s["slug"]) or {"status": "unreachable", "error": "not checked", "tools": []}
    return out


async def list_gateway_tools(user: dict) -> list[Tool]:
    servers = await asyncio.to_thread(db.query, "SELECT * FROM servers WHERE enabled = 1 ORDER BY slug")
    await _ensure_fresh(servers)
    tools: list[Tool] = []
    for s in servers:
        state = _state.get(s["slug"])
        if not state or state["status"] != "connected":
            continue  # a dead server contributes nothing, but never breaks the others
        for t in state["tools"]:
            tools.append(Tool(
                name=f"{s['slug']}__{t.name}",  # the collision scheme: <server>__<tool>
                description=f"[{s['name']}] {t.description or ''}".strip(),
                input_schema=t.input_schema,
            ))
    return tools


async def call_gateway_tool(user: dict, name: str, arguments: dict, source: str = "mcp") -> CallToolResult:
    slug, sep, tool = name.partition("__")
    started = time.perf_counter()
    outcome, error = "success", None
    try:
        server = await asyncio.to_thread(db.one, "SELECT * FROM servers WHERE slug = ?", (slug,)) if sep else None
        if server is None or not server["enabled"]:
            outcome, error = "error", "unknown or disabled tool"
            result = _error(f"Unknown or disabled tool: {name}")
        else:
            with anyio.fail_after(CALL_TIMEOUT):
                async with _connect(server) as client:
                    upstream = await client.call_tool(tool, arguments)
            result = CallToolResult(content=upstream.content, is_error=upstream.is_error)
            if upstream.is_error:
                outcome = "tool_error"
                first_text = next((b.text for b in upstream.content if isinstance(b, TextContent)), "")
                error = first_text.split("\n", 1)[0][:200] or None  # first line only: later lines may echo the arguments
    except TimeoutError:
        outcome, error = "timeout", f"no answer within {CALL_TIMEOUT:g} s"
        result = _error(f"The '{slug}' server did not answer within {CALL_TIMEOUT:g} seconds.")
    except MCPError as exc:
        outcome, error = "error", _describe(exc)
        result = _error(f"The '{slug}' server rejected the call: {exc.message}")
    except Exception as exc:
        outcome, error = "error", _describe(exc)
        forget(slug)  # re-check this server next time
        result = _error(f"The '{slug}' server could not be reached.")
    duration = int((time.perf_counter() - started) * 1000)
    await asyncio.to_thread(
        db.execute,
        "INSERT INTO audit_log(ts, user_id, user_email, source, server_slug, tool, duration_ms, outcome, error) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (db.now(), user["id"], user["email"], source, slug, tool, duration, outcome, (error or "")[:300] or None),
    )
    return result