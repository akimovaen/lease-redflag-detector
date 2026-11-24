import asyncio
import sys

import pytest
from mcp.server.mcpserver import MCPServer

from lease_redflag_detector.agent.registry import DOCUMENTS, FindResult, LeaseRegistry
from lease_redflag_detector.agent.registry_client import RegistryClient
from lease_redflag_detector.agent.registry_server import DESCRIPTIONS, build_server
from lease_redflag_detector.agent.tools import ToolError, TransientError
from lease_redflag_detector.agent.users import get_user
from lease_redflag_detector.extraction.extractor import load_prompt

LEASE = "lease_37032"
REGISTRY = RegistryClient(
    build_server(get_user("lawyer"))
)  # the MCP server, in this process


def test_the_server_describes_its_tools_with_the_versioned_descriptions():
    tools = {t["name"]: t for t in REGISTRY.tools()}
    assert list(tools) == ["find_leases", "get_lease", "read_lease_section"]
    for name, tool in tools.items():
        assert tool["description"] == load_prompt(DESCRIPTIONS[name])
    lease_id = tools["get_lease"]["input_schema"]["properties"]["lease_id"]
    assert lease_id["pattern"] == r"^lease_\d+$"
    assert set(tools["find_leases"]["input_schema"]["properties"]) == {"party", "city"}


def test_the_registry_answers_through_the_server():
    found = REGISTRY.call("find_leases", {"party": "нова пошта"})["leases"]
    assert [lease["lease_id"] for lease in found] == [LEASE]
    info = REGISTRY.summary(LEASE)
    assert info["tenant"] and info["sections"][0]["title"] == "(преамбула)"
    section = REGISTRY.call("read_lease_section", {"lease_id": LEASE, "section": 2})
    assert section["text"] and section["number"] == 2
    assert "Біанчі" in REGISTRY.text(LEASE)


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda r: r.summary("lease_1"), "No lease lease_1 in the registry"),
        (lambda r: r.call("get_lease", {"lease_id": "../etc"}), "should match pattern"),
        (lambda r: r.call("find_leases", {"party": "x" * 101}), "at most 100"),
        (
            lambda r: r.call("read_lease_section", {"lease_id": LEASE, "section": 99}),
            "has 12 sections",
        ),
        (lambda r: r.text("lease_1"), "No lease lease_1 in the registry"),
        (lambda r: r.text("../data/raw"), "Unknown resource"),
    ],
)
def test_the_server_refuses_what_it_does_not_have(call, message):
    with pytest.raises(ToolError, match=message) as error:
        call(REGISTRY)
    assert not isinstance(error.value, TransientError)


def test_an_unexpected_server_error_shows_no_details():
    server = MCPServer("broken", log_level="CRITICAL")

    @server.tool()
    def find_leases() -> dict:
        raise RuntimeError("/Users/someone/data/raw/secret.json")

    with pytest.raises(ToolError) as error:
        RegistryClient(server).call("find_leases", {})
    assert "secret" not in str(error.value)


def test_a_server_that_does_not_answer_is_unavailable_and_the_next_call_reconnects():
    server = MCPServer("slow", log_level="CRITICAL")
    calls = []

    @server.tool()
    async def find_leases() -> FindResult:
        calls.append(1)
        if len(calls) == 1:
            await asyncio.sleep(10)
        return FindResult(leases=[])

    client = RegistryClient(server, timeout_s=0.3)
    with pytest.raises(TransientError, match="registry is unavailable"):
        client.call("find_leases", {})
    assert client.call("find_leases", {}) == {"leases": []}


def test_the_server_runs_as_a_subprocess_over_stdio():
    client = RegistryClient(user="lawyer")
    try:
        assert client.summary(LEASE)["lease_id"] == LEASE
        assert client.server.command == sys.executable
        assert client.server.env == {"REGISTRY_USER": "lawyer"}
    finally:
        client.close()


def test_the_search_excludes_exactly_the_leases_of_the_registry():
    import json

    from lease_redflag_detector.agent.toolset import REGISTRY_TYPES

    excluded = {
        path.stem
        for path in DOCUMENTS.glob("*.json")
        if json.loads(path.read_text(encoding="utf-8"))["meta"].get("type")
        in REGISTRY_TYPES
    }
    assert excluded == set(LeaseRegistry().leases)


def test_an_empty_lease_text_is_an_error():
    server = MCPServer("empty", log_level="CRITICAL")

    @server.resource("lease://{lease_id}")
    def lease_text(lease_id: str) -> str:
        return ""

    with pytest.raises(ToolError, match="no text of lease_1"):
        RegistryClient(server).text("lease_1")


def test_a_server_without_a_registry_tool_is_refused_at_start():
    from lease_redflag_detector.agent.toolset import registry_tool

    server = MCPServer("other", log_level="CRITICAL")

    @server.tool()
    def something() -> FindResult:
        return FindResult(leases=[])

    with pytest.raises(RuntimeError, match="has no tool find_leases"):
        registry_tool(RegistryClient(server), "find_leases", object, object)
