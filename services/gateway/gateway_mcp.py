import asyncio
import contextvars

from mcp.server import ServerRequestContext
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams
from starlette.responses import JSONResponse

import security
import upstream

current_user: contextvars.ContextVar[dict | None] = contextvars.ContextVar("current_user", default=None)


class McpAuth:
    """Pure ASGI middleware. Only /mcp requires a valid API key; everything else passes through."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/mcp"):
            await self.app(scope, receive, send)
            return
        header = dict(scope["headers"]).get(b"authorization", b"").decode("latin-1")
        key = header[7:].strip() if header.lower().startswith("bearer ") else ""
        user = await asyncio.to_thread(security.authenticate_api_key, key) if key else None
        if user is None:
            response = JSONResponse(
                {"error": "invalid_api_key"}, status_code=401, headers={"WWW-Authenticate": 'Bearer realm="gateway"'}
            )
            await response(scope, receive, send)
            return
        token = current_user.set(user)  # visible to the tool handlers for this request only
        try:
            await self.app(scope, receive, send)
        finally:
            current_user.reset(token)


def _user() -> dict:
    user = current_user.get()
    if user is None:
        raise RuntimeError("No authenticated user for this request")
    return user


async def on_list_tools(ctx: ServerRequestContext, params: PaginatedRequestParams | None) -> ListToolsResult:
    return ListToolsResult(tools=await upstream.list_gateway_tools(_user()))


async def on_call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    return await upstream.call_gateway_tool(_user(), params.name, params.arguments or {})