import os
import subprocess
import sys

import pytest

from lease_redflag_detector.agent.registry_client import RegistryClient
from lease_redflag_detector.agent.review import decider
from lease_redflag_detector.agent.tools import TransientError
from lease_redflag_detector.agent.users import UnknownUser, get_user, load_users


def test_the_users_have_known_roles_and_entities():
    users = load_users()
    assert {u: (users[u].role, users[u].entity) for u in users} == {
        "lawyer": ("lawyer", "ТОВ «Орендодавець»"),
        "litigator": ("litigation", "ТОВ «Орендодавець»"),
        "head": ("head_of_legal", "ТОВ «Орендодавець»"),
        "lawyer_b": ("lawyer", "ТОВ «Орендодавець-Б»"),
    }
    assert get_user("head").describe() == (
        "head (керівник юрдепартаменту, ТОВ «Орендодавець»)"
    )


def test_an_unknown_user_role_or_entity_is_refused(tmp_path):
    with pytest.raises(UnknownUser, match="Unknown user 'boss'"):
        get_user("boss")
    with pytest.raises(UnknownUser):
        get_user(None)
    path = tmp_path / "users.toml"
    path.write_text(
        'entities = ["A"]\n[users.x]\nname = "X"\nrole = "admin"\nentity = "A"\n'
    )
    with pytest.raises(ValueError, match="role"):
        load_users(path)
    path.write_text(
        'entities = ["A"]\n[users.x]\nname = "X"\nrole = "lawyer"\nentity = "B"\n'
    )
    with pytest.raises(ValueError, match="unknown entity 'B'"):
        load_users(path)


def test_the_registry_server_does_not_start_for_an_unknown_user():
    env = {k: v for k, v in os.environ.items() if k != "REGISTRY_USER"}
    for user in (None, "boss"):
        if user:
            env["REGISTRY_USER"] = user
        done = subprocess.run(
            [sys.executable, "-m", "lease_redflag_detector.agent.registry_server"],
            env=env,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
        assert done.returncode != 0 and "Unknown user" in done.stderr
    client = RegistryClient(user="boss")
    with pytest.raises(TransientError, match="registry is unavailable"):
        client.tools()


def test_only_a_lawyer_or_the_head_of_legal_records_a_decision():
    assert decider("lawyer_b").id == "lawyer_b"
    assert decider("head").id == "head"
    with pytest.raises(SystemExit, match="may not record decisions"):
        decider("litigator")
    with pytest.raises(SystemExit, match="BY="):
        decider(None)


def make_dry_run(*args: str) -> str:
    return subprocess.run(
        ["make", "-n", *args], capture_output=True, text=True, check=True
    ).stdout


def test_make_starts_as_the_default_user_unless_told_otherwise():
    # AS and USER are taken (make's assembler, the login name): the variable is AS_USER.
    assert "--as" not in make_dry_run("agent", "Q=питання")
    assert "--as litigator" in make_dry_run("agent", "Q=питання", "AS_USER=litigator")
    assert "REGISTRY_USER=lawyer " in make_dry_run("mcp")
    assert "REGISTRY_USER=head " in make_dry_run("mcp", "AS_USER=head")
