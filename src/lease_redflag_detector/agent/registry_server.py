"""The lease registry as an MCP server, read only.

    REGISTRY_USER=lawyer uv run python -m lease_redflag_detector.agent.registry_server
    make mcp [AS_USER=litigator]
    npx @modelcontextprotocol/inspector -e REGISTRY_USER=lawyer uv run python -m \
        lease_redflag_detector.agent.registry_server                 (to try it by hand)

The agent starts it as a subprocess and talks to it over stdio (`registry_client.py`);
Claude Desktop or the MCP Inspector can start it the same way. Every client gets the
same leases through the same checks, so the access rights hold for all of them, the
agent's red flag and redline tools included.

- Tools for a model: find_leases, get_lease, read_lease_section. Their descriptions
  are the versioned files in prompts/tools/.
- Resource lease://{lease_id}: the full text of a lease, for code that reads a whole
  lease (the red flag extractor, the redline generator), not for a model.
- Resource leases://shared: the leases every user of the caller's entity may read,
  the only ones the redline generator may use as market practice.

Nothing here writes, runs a query or opens a path from its arguments: a lease is found
by its id in the registry, filtered by two fields, and every argument is validated.
An expected failure (an unknown lease) goes to the client as its message; any other
error reaches the client without its details.

The server works for one user, named when it starts (`REGISTRY_USER`, a user of
configs/users.toml); a client cannot change it during the session. Without a known
user the server does not start.

What the user may read is decided here, by the rules of `access.py`: a lease the user
may not read is refused with the reason by every tool and by the text resource, and a
lease of another legal entity is not listed. A lease id the user already knows still
gets the reason, not a pretence that the lease does not exist.
"""

import os
import re
import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import (
    ResourceError,
    ResourceNotFoundError,
    ToolError,
)
from mcp.types import ToolAnnotations

from lease_redflag_detector.agent.access import Access
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
SHARED_URI = "leases://shared"
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
# The versioned descriptions of the tools (prompts/tools/).
DESCRIPTIONS = {
    "find_leases": "tools/find_leases_v2",
    "get_lease": "tools/get_lease_v1",
    "read_lease_section": "tools/read_lease_section_v1",
}


def build_server(
    user: User, registry: LeaseRegistry | None = None, access: Access | None = None
) -> MCPServer:
    registry = registry or LeaseRegistry()
    access = access or Access()
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
            description=load_prompt(DESCRIPTIONS[name]),
            annotations=READ_ONLY,
        )

    def readable(lease_id: str) -> None:
        """Raise ToolError if the lease does not exist or the user may not read it."""
        try:
            registry.lease(lease_id)
        except LeaseNotFound as e:
            raise ToolError(str(e)) from None
        if denial := access.denial(user, lease_id):
            raise ToolError(denial)

    @tool("find_leases")
    def find_leases(party: Party = None, city: City = None) -> FindResult:
        return FindResult(
            leases=[
                lease | {"restricted": access.restriction(user, lease["lease_id"])}
                for lease in registry.find(party, city)
                if access.listed(user, lease["lease_id"])
            ]
        )

    @tool("get_lease")
    def get_lease(lease_id: LeaseId) -> LeaseInfo:
        readable(lease_id)
        summary = registry.summary(lease_id)
        sections = registry.sections(lease_id)
        return LeaseInfo(
            **summary,
            sections=[SectionTitle(number=s.number, title=s.title) for s in sections],
        )

    @tool("read_lease_section")
    def read_lease_section(lease_id: LeaseId, section: SectionNumber) -> SectionText:
        readable(lease_id)
        sections = registry.sections(lease_id)
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
            registry.lease(lease_id)
        except LeaseNotFound as e:
            raise ResourceNotFoundError(str(e)) from None
        if denial := access.denial(user, lease_id):
            raise ResourceError(denial)
        return registry.text(lease_id)

    @server.resource(
        SHARED_URI,
        name="shared_leases",
        description=(
            "The ids of the leases every user of the caller's entity may read, one per "
            "line: the only leases a redline may use as market practice."
        ),
        mime_type="text/plain",
    )
    def shared_leases() -> str:
        return "\n".join(
            lease_id for lease_id in registry.leases if access.shared(user, lease_id)
        )

    return server


def main() -> None:
    try:
        user = get_user(os.environ.get(USER_ENV))
    except UnknownUser as e:
        sys.exit(f"{NAME}: {e} Set {USER_ENV}.")
    build_server(user).run("stdio")


if __name__ == "__main__":
    main()
