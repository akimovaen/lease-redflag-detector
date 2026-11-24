"""The agent's connection to the lease registry MCP server (`registry_server.py`).

The agent learns the registry's tools from the server (`tools`), as any MCP client
does, and calls them by name (`call`); the full text of a lease is a resource
(`text`). The loop of the agent is synchronous and MCP is asynchronous, so the
connection lives on its own event loop in a background thread, and every call waits
for its answer there.

By default the server is started as a subprocess over stdio, with only the safe
environment variables of the MCP SDK: the API keys stay with the agent. Who works with
the agent goes to the server when it starts (`REGISTRY_USER`), not as an argument of a
tool, so that the model cannot change it.

Failures:
- what the server answers as a failure (an unknown lease, invalid arguments) raises
  `ToolError` with its message;
- a server that does not answer in time or whose connection broke raises
  `TransientError`; the next call starts the server again.
"""

import asyncio
import atexit
import sys
import threading
from collections.abc import Callable, Coroutine
from typing import Any

from mcp import Client, StdioServerParameters
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError
from mcp.types import CONNECTION_CLOSED, REQUEST_TIMEOUT

from lease_redflag_detector.agent.registry_server import TEXT_URI, USER_ENV
from lease_redflag_detector.agent.tools import ToolError, TransientError

TIMEOUT_S = 10.0
LOST = (CONNECTION_CLOSED, REQUEST_TIMEOUT)


def stdio_server(user: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "lease_redflag_detector.agent.registry_server"],
        env={USER_ENV: user},
    )


def unavailable(error: BaseException) -> TransientError:
    detail = str(error) or type(error).__name__
    return TransientError(f"The lease registry is unavailable: {detail}.")


class RegistryClient:
    def __init__(
        self,
        server: MCPServer | StdioServerParameters | None = None,
        user: str = "lawyer",
        timeout_s: float = TIMEOUT_S,
    ):
        """`server`: an MCPServer runs in this process (tests), built for `user`; by
        default the server is a subprocess started for `user`."""
        self.user = user
        self.server = server or stdio_server(user)
        self.timeout_s = timeout_s
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.client: Client | None = None
        self.stop: asyncio.Event | None = None
        self.lock = asyncio.Lock()
        self._tools: list[dict] | None = None
        atexit.register(self.close)

    # The connection, on the background loop

    async def connect(self) -> Client:
        async with self.lock:
            if self.client is None:
                ready, failed = asyncio.Event(), []
                self.stop = asyncio.Event()
                self.loop.create_task(self.hold(ready, failed, self.stop))
                await ready.wait()
                if failed:
                    raise failed[0]
            return self.client

    async def hold(self, ready: asyncio.Event, failed: list, stop: asyncio.Event):
        """Keep one connection open until `stop`: it is opened and closed in one task."""
        client = None
        try:
            async with Client(self.server, read_timeout_seconds=self.timeout_s) as c:
                self.client = client = c
                ready.set()
                await stop.wait()
        except Exception as e:  # noqa: BLE001 - the waiting call raises it
            failed.append(e)
        finally:
            # A new connection may be open by now; only this one is gone.
            if self.client is client:
                self.client = None
            ready.set()

    async def drop(self) -> None:
        if self.stop:
            self.stop.set()
        self.client = None

    def run(self, call: Callable[[Client], Coroutine[Any, Any, Any]]):
        """Run `call` with the connection and wait for it; a lost connection is
        dropped, so that the next call opens a new one."""

        async def main():
            try:
                return await call(await self.connect())
            except MCPError as e:
                if e.code in LOST:
                    await self.drop()
                    raise unavailable(e) from e
                raise ToolError(e.error.message) from e
            except (ToolError, asyncio.CancelledError):
                raise
            except Exception as e:  # a broken transport, a dead server
                await self.drop()
                raise unavailable(e) from e

        future = asyncio.run_coroutine_threadsafe(main(), self.loop)
        try:
            return future.result(self.timeout_s + 5)
        except TimeoutError as e:
            future.cancel()
            asyncio.run_coroutine_threadsafe(self.drop(), self.loop)
            raise unavailable(e) from e

    def close(self) -> None:
        if self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.drop(), self.loop).result(5)

    # What the agent uses

    def tools(self) -> list[dict]:
        """The registry's tools as the model sees them: name, description, schema."""
        if self._tools is None:
            listed = self.run(lambda c: c.list_tools())
            self._tools = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in listed.tools
            ]
        return self._tools

    def call(self, name: str, args: dict) -> dict:
        """The structured result of a tool; its failure raises ToolError."""
        result = self.run(lambda c: c.call_tool(name, args))
        text = " ".join(getattr(block, "text", "") for block in result.content)
        if result.is_error:
            raise ToolError(text.removeprefix(f"Error executing tool {name}: "))
        if result.structured_content is None:
            raise ToolError(f"{name} returned no structured result.")
        return result.structured_content

    def text(self, lease_id: str) -> str:
        uri = TEXT_URI.format(lease_id=lease_id)
        result = self.run(lambda c: c.read_resource(uri))
        text = "".join(getattr(content, "text", "") for content in result.contents)
        if not text.strip():
            raise ToolError(f"The registry returned no text of {lease_id}.")
        return text

    def summary(self, lease_id: str) -> dict:
        return self.call("get_lease", {"lease_id": lease_id})
