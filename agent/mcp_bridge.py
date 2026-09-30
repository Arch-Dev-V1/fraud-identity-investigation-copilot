"""A synchronous facade over an asynchronous MCP client.

Streamlit runs synchronously and the loop in loop.py is a plain generator, but
the MCP client is async and holds an anyio task group open for the life of the
session. Entering that context in one task and calling it from another raises
anyio cancel-scope errors, so this bridge does the one thing that is safe: it
runs a single long-lived coroutine on a dedicated event loop in a background
thread, and that coroutine both holds the session open and services every
request off a queue. Enter, call and exit therefore all happen in one task.
"""

from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import Future
from typing import Any, Callable

from mcp import Client, StdioServerParameters

DEFAULT_STARTUP_TIMEOUT = 30.0
DEFAULT_CALL_TIMEOUT = 30.0


class McpUnavailable(RuntimeError):
    """The MCP server could not be reached or started."""


class McpBridge:
    """Talk to an MCP server from synchronous code.

    ``target`` is anything the MCP Client accepts: ``StdioServerParameters`` to
    launch a server as a subprocess, a URL string for streamable HTTP, or an
    ``MCPServer`` instance to connect in-process (which is what the tests use,
    so they need no subprocess and no network).
    """

    def __init__(
        self,
        target: Any,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
        call_timeout: float = DEFAULT_CALL_TIMEOUT,
    ) -> None:
        self._target = target
        self._startup_timeout = startup_timeout
        self._call_timeout = call_timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._closed = False

    # --- lifecycle

    def start(self) -> "McpBridge":
        if self._thread is not None:
            return self
        self._thread = threading.Thread(
            target=lambda: asyncio.run(self._serve()),
            name="mcp-bridge",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(self._startup_timeout):
            raise McpUnavailable(
                f"MCP server did not become ready within {self._startup_timeout}s."
            )
        if self._startup_error is not None:
            raise McpUnavailable(f"Could not start the MCP server: {self._startup_error}")
        return self

    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        try:
            async with Client(self._target) as client:
                self._ready.set()
                while True:
                    job = await self._queue.get()
                    if job is None:
                        break
                    work, future = job
                    if future.set_running_or_notify_cancel():
                        try:
                            future.set_result(await work(client))
                        except Exception as exc:  # a failed call must not kill the session
                            future.set_exception(exc)
        except BaseException as exc:
            self._startup_error = exc
            raise
        finally:
            self._ready.set()   # unblock start() even on failure

    def close(self) -> None:
        if self._closed or self._loop is None or self._queue is None:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
        if self._thread is not None:
            self._thread.join(timeout=10)

    def __enter__(self) -> "McpBridge":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- calls

    def _submit(self, work: Callable[[Client], Any]) -> Any:
        if self._loop is None or self._queue is None:
            raise McpUnavailable("Bridge is not started. Call start() first.")
        if self._closed:
            raise McpUnavailable("Bridge is closed.")
        future: Future = Future()
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (work, future))
        return future.result(timeout=self._call_timeout)

    def list_tools(self) -> list[Any]:
        return self._submit(lambda client: _list_tools(client))

    def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        """Call one MCP tool. Returns ``(text_payload, is_error)``."""
        return self._submit(lambda client: _call_tool(client, name, arguments))


async def _list_tools(client: Client) -> list[Any]:
    return list((await client.list_tools()).tools)


async def _call_tool(client: Client, name: str, arguments: dict) -> tuple[str, bool]:
    result = await client.call_tool(name, arguments)
    # mcp renamed isError -> is_error between major versions; tolerate both.
    is_error = bool(getattr(result, "is_error", None) or getattr(result, "isError", False))
    texts = [
        block.text
        for block in (result.content or [])
        if getattr(block, "type", None) == "text"
    ]
    payload = "\n".join(texts) if texts else json.dumps({"error": "empty tool result"})
    # A tool that returns its own {"error": ...} is a failed lookup even when
    # the protocol call itself succeeded.
    if not is_error:
        try:
            parsed = json.loads(payload)
            is_error = isinstance(parsed, dict) and "error" in parsed
        except json.JSONDecodeError:
            pass
    return payload, is_error


def anthropic_tool_definitions(mcp_tools: list[Any]) -> list[dict]:
    """Convert MCP tool descriptors into Claude tool definitions.

    ``strict`` requires ``additionalProperties: false``, which MCP's generated
    schemas do not set, so it is added here — the lookups take exactly one
    argument and nothing else should ever be accepted.
    """
    definitions = []
    for tool in mcp_tools:
        schema = dict(tool.input_schema or {})
        schema.setdefault("type", "object")
        schema["additionalProperties"] = False
        # A strict schema must list every property as required.
        schema["required"] = sorted(schema.get("properties", {}))
        definitions.append({
            "name": tool.name,
            "description": tool.description or "",
            "strict": True,
            "input_schema": schema,
        })
    return definitions


def stdio_target(python_executable: str | None = None) -> StdioServerParameters:
    """Launch this project's MCP server as a subprocess over stdio."""
    import sys

    return StdioServerParameters(
        command=python_executable or sys.executable,
        args=["-m", "mcp_server"],
    )
