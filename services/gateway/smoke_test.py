import json
import os
import sys

import anyio
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8300/mcp")


def parse(value: str):
    try:
        return json.loads(value)
    except ValueError:
        return value


async def main() -> None:
    tool = sys.argv[1] if len(sys.argv) > 1 else None
    args = {k: parse(v) for k, v in (a.split("=", 1) for a in sys.argv[2:])}
    headers = {"Authorization": f"Bearer {os.environ['GATEWAY_KEY']}"}
    async with httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(30.0, read=120.0)) as http:
        async with Client(streamable_http_client(URL, http_client=http)) as client:
            if tool is None:
                for t in (await client.list_tools()).tools:
                    print(t.name)
                return
            result = await client.call_tool(tool, args)
            print("is_error:", result.is_error)
            for block in result.content:
                print(getattr(block, "text", block))


try:
    anyio.run(main)
except Exception as exc:
    print(f"{type(exc).__name__}: {exc}")