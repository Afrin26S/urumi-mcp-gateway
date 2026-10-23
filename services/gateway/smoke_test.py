
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

    args = {
        key: parse(value)
        for key, value in (
            item.split("=", 1) for item in sys.argv[2:]
        )
    }

    api_key = os.environ.get("GATEWAY_KEY")
    if not api_key:
        print("Error: GATEWAY_KEY environment variable is not set.")
        return

    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx2.AsyncClient(
        headers=headers,
        timeout=httpx2.Timeout(30.0, read=120.0),
    ) as http:
        async with Client(
            streamable_http_client(URL, http_client=http)
        ) as client:
            if tool is None:
                result = await client.list_tools()
                for item in result.tools:
                    print(item.name)
                return

            result = await client.call_tool(tool, args)
            print("is_error:", result.is_error)

            for block in result.content:
                print(getattr(block, "text", block))


def print_exception(exc: BaseException, indent: int = 0) -> None:
    prefix = " " * indent
    print(f"{prefix}{type(exc).__name__}: {exc}")

    # Print every nested exception inside an ExceptionGroup.
    for item in getattr(exc, "exceptions", ()):
        print_exception(item, indent + 2)

    # Print the underlying cause, when available.
    cause = getattr(exc, "__cause__", None)
    if cause is not None:
        print(f"{prefix}Caused by:")
        print_exception(cause, indent + 2)


if __name__ == "__main__":
    try:
        anyio.run(main)
    except Exception as exc:
        print_exception(exc)
        sys.exit(1)
