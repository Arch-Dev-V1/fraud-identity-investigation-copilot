"""Entry point: ``python -m mcp_server [--transport stdio|streamable-http]``."""

from __future__ import annotations

import argparse

from .server import server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "streamable-http", "sse"],
        help="stdio (default) is what the agent launches; use streamable-http "
             "to serve other MCP clients over the network.",
    )
    args = parser.parse_args()
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()
