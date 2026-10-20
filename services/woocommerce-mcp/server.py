import os
from datetime import date
from typing import Literal

import httpx
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

load_dotenv()  # reads .env when developing locally; in Kubernetes the variables come from a Secret

WC_BASE_URL = os.environ["WC_BASE_URL"].rstrip("/")
WC_KEY = os.environ["WC_CONSUMER_KEY"]
WC_SECRET = os.environ["WC_CONSUMER_SECRET"]
FORWARD_HTTPS = os.getenv("WC_FORWARD_HTTPS", "false").lower() == "true"

mcp = MCPServer("woocommerce")

# Fixed sets of allowed values. The SDK turns these into an "enum" in the tool's schema.
OrderFilter = Literal["any", "pending", "processing", "on-hold", "completed", "cancelled", "refunded", "failed"]
SettableStatus = Literal["processing", "on-hold", "completed", "cancelled"]


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


def _error_message(resp: httpx.Response) -> str:
    try:
        message = resp.json().get("message", "no details")
    except (ValueError, AttributeError):
        message = "no details"
    return f"The store returned HTTP {resp.status_code}: {message}"


async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    """The single place where we talk to WooCommerce, so errors are handled once."""
    try:
        async with _client() as client:
            resp = await client.request(method, path, **kwargs)
    except httpx.TimeoutException as exc:
        raise ToolError("The store did not answer within 10 seconds. Try again shortly.") from exc
    except httpx.HTTPError as exc:
        raise ToolError(f"Could not reach the store ({type(exc).__name__}).") from exc
    if resp.status_code >= 400:
        raise ToolError(_error_message(resp))
    return resp


def _product_summary(p: dict) -> dict:
    return {
        "id": p["id"],
        "name": p["name"],
        "price": p["price"],
        "status": p["status"],
        "stock_status": p["stock_status"],
        "sku": p["sku"],
    }


def _order_summary(o: dict) -> dict:
    billing = o.get("billing", {})
    return {
        "id": o["id"],
        "status": o["status"],
        "total": o["total"],
        "currency": o["currency"],
        "created": o["date_created"],
        "customer": f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip(),
        "payment_method": o.get("payment_method_title", ""),
        "items": [
            {"product_id": i["product_id"], "name": i["name"], "quantity": i["quantity"], "total": i["total"]}
            for i in o.get("line_items", [])
        ],
    }


def _parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"{field} must be a date written like 2026-10-21.") from None


@mcp.tool()
async def list_products(page: int = 1, per_page: int = 10, search: str | None = None) -> dict:
    """List products in the store, newest first. Returns id, name, price, status, stock status and SKU."""
    params = {"page": page, "per_page": min(per_page, 50)}
    if search:
        params["search"] = search
    resp = await _request("GET", "/products", params=params)
    return {
        "total": int(resp.headers.get("X-WP-Total", 0)),
        "page": page,
        "products": [_product_summary(p) for p in resp.json()],
    }


@mcp.tool()
async def create_product(
    name: str,
    price: float,
    description: str = "",
    status: Literal["publish", "draft"] = "publish",
) -> dict:
    """Create a simple product. Price is a plain number such as 299 or 49.99.
    Use status 'publish' to show it on the storefront, or 'draft' to keep it hidden."""
    name = name.strip()
    if not name:
        raise ToolError("The product name must not be empty.")
    if price < 0:
        raise ToolError("The price must not be negative.")
    body = {
        "name": name,
        "type": "simple",
        "regular_price": f"{price:.2f}",
        "description": description,
        "status": status,
    }
    resp = await _request("POST", "/products", json=body)
    return _product_summary(resp.json())


@mcp.tool()
async def list_orders(
    status: OrderFilter = "any",
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    per_page: int = 10,
) -> dict:
    """List orders, newest first. Optionally filter by status and by creation date.
    Dates are written YYYY-MM-DD and both ends are inclusive, so for today's orders
    pass today's date as both date_from and date_to."""
    params = {
        "status": status,
        "page": page,
        "per_page": min(per_page, 50),
        "orderby": "date",
        "order": "desc",
    }
    if date_from:
        params["after"] = f"{_parse_date(date_from, 'date_from').isoformat()}T00:00:00"
    if date_to:
        params["before"] = f"{_parse_date(date_to, 'date_to').isoformat()}T23:59:59"
    resp = await _request("GET", "/orders", params=params)
    return {
        "total": int(resp.headers.get("X-WP-Total", 0)),
        "page": page,
        "orders": [_order_summary(o) for o in resp.json()],
    }


@mcp.tool()
async def get_order(order_id: int) -> dict:
    """Get one order by its id, including the items bought and any note left by the customer."""
    resp = await _request("GET", f"/orders/{order_id}")
    order = resp.json()
    return _order_summary(order) | {"customer_note": order.get("customer_note", "")}


@mcp.tool()
async def update_order_status(order_id: int, status: SettableStatus) -> dict:
    """Change an order's status to processing, on-hold, completed or cancelled.
    Refunds are not supported by this tool."""
    resp = await _request("PUT", f"/orders/{order_id}", json={"status": status})
    return _order_summary(resp.json())


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        stateless_http=True,
        json_response=True,
    )