"""The lease registry as an MCP server, read only.

    REGISTRY_USER=lawyer uv run python -m lease_redflag_detector.agent.registry_server
    make mcp [AS_USER=litigator]
    npx @modelcontextprotocol/inspector uv run python -m \
        lease_redflag_detector.agent.registry_server                 (to try it by hand)

The agent starts it as a subprocess and talks to it over stdio (`registry_client.py`);
Claude Desktop or the MCP Inspector can start it the same way. Every client gets the
same leases through the same checks, so the access rights added in step 2.3 hold for
all of them, the agent's search and redline tools included.

- Tools for a model: find_leases, get_lease, read_lease_section. Their descriptions
  are the versioned files in prompts/tools/.
- Resource lease://{lease_id}: the full text of a lease, for code that reads a whole
  lease (the red flag extractor, the redline generator), not for a model.

Nothing here writes, runs a query or opens a path from its arguments: a lease is found
by its id in the registry, filtered by two fields, and every argument is validated.
An expected failure (an unknown lease) goes to the client as its message; any other
error reaches the client without its details.

The server works for one user, named when it starts (`REGISTRY_USER`, a user of
configs/users.toml); a client cannot change it during the session. Without a known
user the server does not start. What the user may read is checked from step 2.3.
"""

import os
import re
import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceNotFoundError, ToolError
from mcp.types import ToolAnnotations

from lease_redflag_detector.agent.registry import (
    LEASE_ID,
    City,
    FindResult,
    LeaseId,
    LeaseInfo,
    LeaseNotFound,
    LeaseRegistry,
    Party,
    SectionNumber,
    SectionText,
    SectionTitle,
)
from lease_redflag_detector.agent.users import UnknownUser, User, get_user
from lease_redflag_detector.extraction.extractor import load_prompt

NAME = "lease-registry"
USER_ENV = "REGISTRY_USER"
TEXT_URI = "lease://{lease_id}"
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def build_server(user: User, registry: LeaseRegistry | None = None) -> MCPServer:
    registry = registry or LeaseRegistry()
    server = MCPServer(
        NAME,
        instructions=(
            "The landlord's lease registry: find a lease, read its sections. "
            f"Working for {user.describe()}."
        ),
        log_level="WARNING",
    )

    def tool(name: str):
        return server.tool(
            name=name,
            description=load_prompt(f"tools/{name}_v1"),
            annotations=READ_ONLY,
        )

    @tool("find_leases")
    def find_leases(party: Party = None, city: City = None) -> FindResult:
        return FindResult(leases=registry.find(party, city))

    @tool("get_lease")
    def get_lease(lease_id: LeaseId) -> LeaseInfo:
        try:
            summary = registry.summary(lease_id)
            sections = registry.sections(lease_id)
        except LeaseNotFound as e:
            raise ToolError(str(e)) from None
        return LeaseInfo(
            **summary,
            sections=[SectionTitle(number=s.number, title=s.title) for s in sections],
        )

    @tool("read_lease_section")
    def read_lease_section(lease_id: LeaseId, section: SectionNumber) -> SectionText:
        try:
            sections = registry.sections(lease_id)
        except LeaseNotFound as e:
            raise ToolError(str(e)) from None
        if section > len(sections):
            raise ToolError(f"{lease_id} has {len(sections)} sections.")
        found = sections[section - 1]
        return SectionText(
            lease_id=lease_id, number=found.number, title=found.title, text=found.text
        )

    @server.resource(
        TEXT_URI,
        name="lease_text",
        description="The full text of a lease.",
        mime_type="text/plain",
    )
    def lease_text(lease_id: str) -> str:
        try:
            if not re.fullmatch(LEASE_ID, lease_id):
                raise LeaseNotFound(lease_id)
            return registry.text(lease_id)
        except LeaseNotFound as e:
            raise ResourceNotFoundError(str(e)) from None

    return server


def main() -> None:
    try:
        user = get_user(os.environ.get(USER_ENV))
    except UnknownUser as e:
        sys.exit(f"{NAME}: {e} Set {USER_ENV}.")
    build_server(user).run("stdio")


if __name__ == "__main__":
    main()
