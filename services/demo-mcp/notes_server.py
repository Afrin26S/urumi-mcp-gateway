import os

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

mcp = MCPServer("notes")

NOTES: list[str] = []  # lives in memory only; lost on restart, which is fine for a demo


@mcp.tool()
async def add_note(text: str) -> dict:
    """Save a short note and return its number."""
    text = text.strip()
    if not text:
        raise ToolError("The note must not be empty.")
    NOTES.append(text)
    return {"note_id": len(NOTES), "text": text}


@mcp.tool()
async def list_notes() -> dict:
    """List all saved notes."""
    return {"notes": [{"note_id": i + 1, "text": t} for i, t in enumerate(NOTES)]}


@mcp.tool()
async def search(query: str) -> dict:
    """Search the saved notes for a word or phrase."""
    q = query.lower()
    return {"matches": [{"note_id": i + 1, "text": t} for i, t in enumerate(NOTES) if q in t.lower()]}


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        stateless_http=True,
        json_response=True,
    )