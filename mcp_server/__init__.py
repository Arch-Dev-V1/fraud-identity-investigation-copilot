"""MCP server exposing the investigation lookups as MCP tools.

The tools are thin: each one calls the provider gateway over HTTP and returns
the JSON. Keeping them thin is the point — the server is a transport surface,
not a place for logic, so the same tools can be consumed by this app's agent,
by Claude Desktop, or by anything else that speaks MCP.
"""
