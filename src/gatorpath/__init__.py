def main() -> None:
    """`uv run gatorpath`: the MCP server over stdio."""
    from gatorpath.server import mcp

    mcp.run()
