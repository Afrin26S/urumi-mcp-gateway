import os

import httpx
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

load_dotenv()  # reads .env when developing locally; in Kubernetes the variables come from a Secret

WC_BASE_URL = os.environ["WC_BASE_URL"].rstrip("/")
WC_KEY = os.environ["WC_CONSUMER_KEY"]
WC_SECRET = os.environ["WC_CONSUMER_SECRET"]
FORWARD_HTTPS = os.getenv("WC_FORWARD_HTTPS", "false").lower() == "true"

mcp = MCPServer("woocommerce")


def _client() -> httpx.AsyncClient:
    headers = {"Accept": "application/json"}
    if FORWARD_HTTPS:
        headers["X-Forwarded-Proto"] = "https"
    return httpx.AsyncClient(
        base_url=f"{WC_BASE_URL}/wp-json/wc/v3",
        auth=(WC_KEY, WC_SECRET),
        headers=headers,
        timeout=10.0,
    )


@mcp.tool()
async def list_products(page: int = 1, per_page: int = 10, search: str | None = None) -> dict:
    """List products in the store, newest first. Returns id, name, price, status, stock status and SKU."""
    params = {"page": page, "per_page": min(per_page, 50)}
    if search:
        params["search"] = search
    async with _client() as client:
        resp = await client.get("/products", params=params)
    resp.raise_for_status()
    products = [
        {
            "id": p["id"],
            "name": p["name"],
            "price": p["price"],
            "status": p["status"],
            "stock_status": p["stock_status"],
            "sku": p["sku"],
        }
        for p in resp.json()
    ]
    return {"total": int(resp.headers.get("X-WP-Total", 0)), "page": page, "products": products}


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        stateless_http=True,
        json_response=True,
    )