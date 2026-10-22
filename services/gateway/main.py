import config  # noqa: F401
import bootstrap

bootstrap.run()  # create tables, first admin and the three seed servers (only if empty)

from mcp.server import Server  # noqa: E402

from api import api  # noqa: E402
from gateway_mcp import McpAuth, on_call_tool, on_list_tools  # noqa: E402

server = Server("gateway", version="0.1.0", on_list_tools=on_list_tools, on_call_tool=on_call_tool)

app = server.streamable_http_app(json_response=True, stateless_http=True, host="0.0.0.0")
app.add_middleware(McpAuth)
app.mount("/api", api)