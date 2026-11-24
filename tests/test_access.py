import pytest

from lease_redflag_detector.agent.access import DENIED, Access
from lease_redflag_detector.agent.loop import ToolCall
from lease_redflag_detector.agent.registry import LeaseRegistry
from lease_redflag_detector.agent.registry_client import RegistryClient
from lease_redflag_detector.agent.registry_server import build_server
from lease_redflag_detector.agent.tools import AccessDenied
from lease_redflag_detector.agent.users import get_user, load_users

LITIGATION, OTHER_ENTITY, NDA = "lease_35532", "lease_56855", "lease_92441"
OPEN = "lease_37032"
CLIENTS = {
    user: RegistryClient(build_server(get_user(user)), user=user)
    for user in ("lawyer", "litigator", "head", "lawyer_b")
}


def test_the_marks_name_leases_of_the_registry_and_known_entities():
    access = Access()
    assert set(access.marks) <= set(LeaseRegistry().leases)
    entities = {u.entity for u in load_users().values()}
    assert {access.entity(lease) for lease in access.marks} <= entities


@pytest.mark.parametrize(
    ("lease", "reason", "readers"),
    [
        (LITIGATION, "court dispute; only the litigation team", {"litigator"}),
        (
            OTHER_ENTITY,
            "another legal entity of the group (ТОВ «Орендодавець-Б»)",
            {"lawyer_b"},
        ),
        (NDA, "NDA with an anchor tenant; only the head of legal", {"head"}),
    ],
)
def test_each_reason_refuses_everyone_but_its_readers(lease, reason, readers):
    for user, client in CLIENTS.items():
        reads = [
            lambda c=client: c.summary(lease),
            lambda c=client: c.call(
                "read_lease_section", {"lease_id": lease, "section": 1}
            ),
            lambda c=client: c.text(lease),
        ]
        for read in reads:
            if user in readers:
                assert read()
                continue
            # another entity is checked first: its users get that reason
            other = Access().entity(lease) != get_user(user).entity
            expected = "another legal entity" if other else reason
            with pytest.raises(AccessDenied, match=expected) as error:
                read()
            assert str(error.value).startswith(f"{DENIED}: {lease}")


def test_a_lease_of_another_entity_is_not_listed_and_restricted_ones_are_marked():
    def listed(user):
        return {
            x["lease_id"]: x["restricted"]
            for x in CLIENTS[user].call("find_leases", {})["leases"]
        }

    lawyer = listed("lawyer")
    assert OTHER_ENTITY not in lawyer
    assert "court dispute" in lawyer[LITIGATION] and "NDA" in lawyer[NDA]
    assert lawyer[OPEN] is None
    assert listed("litigator")[LITIGATION] is None
    assert listed("head")[NDA] is None
    assert listed("lawyer_b") == {OTHER_ENTITY: None}


def test_market_practice_comes_only_from_leases_open_to_the_whole_entity():
    shared = {user: client.shared() for user, client in CLIENTS.items()}
    # the head may read the NDA lease, but a redline goes to the queue: not shared
    assert shared["head"] == shared["lawyer"] == shared["litigator"]
    assert not {LITIGATION, NDA, OTHER_ENTITY} & shared["lawyer"]
    assert OPEN in shared["lawyer"]
    assert shared["lawyer_b"] == {OTHER_ENTITY}


def test_a_denial_is_its_own_kind_of_tool_error_and_is_not_retried():
    from lease_redflag_detector.agent.registry import LeaseArgs, LeaseInfo
    from lease_redflag_detector.agent.tools import Toolbox
    from lease_redflag_detector.agent.toolset import registry_tool

    box = Toolbox([registry_tool(CLIENTS["lawyer"], "get_lease", LeaseArgs, LeaseInfo)])
    result = box.execute(ToolCall("1", "get_lease", {"lease_id": NDA}))
    assert result.is_error and result.error_kind == "denied"
    assert result.content.startswith(f"{DENIED}: {NDA}")
    assert result.error_kind not in {"transient", "timeout"}  # loop.RETRYABLE
