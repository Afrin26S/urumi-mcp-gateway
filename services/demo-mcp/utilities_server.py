import asyncio
import hmac
import os

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

TOKEN = os.environ["UTILS_TOKEN"]

mcp = MCPServer("utilities")

# Fixed DEMO rates: units of each currency per 1 USD. They are not real market rates.
RATES = {"USD": 1.0, "INR": 88.0, "EUR": 0.92, "GBP": 0.79}

FAQ = {
    "shipping": "Orders ship within 2 business days.",
    "returns": "Items can be returned within 14 days.",
    "payment": "We accept cash on delivery.",
}


@mcp.tool()
async def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """Convert an amount between USD, INR, EUR and GBP using fixed demo rates (not live rates)."""
    src, dst = from_currency.upper(), to_currency.upper()
    if src not in RATES or dst not in RATES:
        raise ToolError(f"Supported currencies are: {', '.join(RATES)}.")
    converted = amount / RATES[src] * RATES[dst]
    return {"amount": amount, "from": src, "to": dst, "result": round(converted, 2)}


@mcp.tool()
async def search(query: str) -> dict:
    """Search the store FAQ (topics: shipping, returns, payment)."""
    q = query.lower()
    return {"answers": [{"topic": k, "answer": v} for k, v in FAQ.items() if q in k or q in v.lower()]}


@mcp.tool()
async def slow_echo(text: str, seconds: float = 5) -> dict:
    """Wait for the given number of seconds (0 to 60), then repeat the text. Used to test timeouts."""
    await asyncio.sleep(min(max(seconds, 0), 60))
    return {"text": text}


class RequireBearer:
    """Reject every HTTP request that does not carry the expected bearer token."""

    def __init__(self, app, token: str):
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            supplied = dict(scope["headers"]).get(b"authorization", b"")
            if not hmac.compare_digest(supplied, self.expected):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
                return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    app = mcp.streamable_http_app(json_response=True, stateless_http=True, host="0.0.0.0")
    uvicorn.run(RequireBearer(app, TOKEN), host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))