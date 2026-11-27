import json

import pytest

from lease_redflag_detector.agent.confirm import ScriptedConfirmer
from lease_redflag_detector.agent.memory import (
    ACTIVE,
    FORGOTTEN,
    REPLACED,
    NoteStore,
    policy_version,
)
from lease_redflag_detector.agent.registry_client import RegistryClient
from lease_redflag_detector.agent.registry_server import build_server
from lease_redflag_detector.agent.tools import AccessDenied, ToolError
from lease_redflag_detector.agent.toolset import (
    ForgetArgs,
    Memory,
    RecallArgs,
    RememberArgs,
    forget,
    recall_notes,
    remember,
)
from lease_redflag_detector.agent.users import get_user

VERSION = policy_version()
OPEN, NDA = "lease_55572", "lease_92441"
ENTITY_A, ENTITY_B = "ТОВ «Орендодавець»", "ТОВ «Орендодавець-Б»"
CLIENTS = {
    user: RegistryClient(build_server(get_user(user)), user=user)
    for user in ("lawyer", "head", "lawyer_b")
}


def memory(tmp_path, user="lawyer"):
    return Memory(NoteStore(tmp_path / "memory.db"), CLIENTS[user], get_user(user))


def test_the_version_is_the_policy_in_force():
    assert VERSION == "policy_2026+policy_2026_amendment_1"


def test_a_new_note_on_the_same_lease_and_topic_replaces_the_old(tmp_path):
    store = NoteStore(tmp_path / "m.db")
    first, created = store.add(
        "3 % не погоджуємо.", "lawyer", ENTITY_A, VERSION, OPEN, "indexation_limited"
    )
    assert created and first.id == "N-0001"
    again, created = store.add(
        "3 % не погоджуємо.", "lawyer", ENTITY_A, VERSION, OPEN, "indexation_limited"
    )
    assert not created and again.id == first.id  # the same note is not kept twice
    other, _ = store.add(
        "Розірвання — ні.", "lawyer", ENTITY_A, VERSION, OPEN, "tenant_break_option"
    )
    second, _ = store.add(
        "5 % — теж ні.", "lawyer", ENTITY_A, VERSION, OPEN, "indexation_limited"
    )
    assert store.get(first.id).status == REPLACED
    assert store.get(first.id).replaced_by == second.id
    assert store.get(other.id).status == ACTIVE  # another topic stays
    general = [
        store.add(f"Загальна {n}.", "lawyer", ENTITY_A, VERSION)[0] for n in (1, 2)
    ]
    assert all(store.get(n.id).status == ACTIVE for n in general)  # never replaced


def test_a_note_of_another_policy_version_is_not_in_force(tmp_path):
    store = NoteStore(tmp_path / "m.db")
    store.add(
        "Поступки погоджує комерційний директор.", "lawyer", ENTITY_A, "policy_2026"
    )
    assert store.active(VERSION) == []
    assert len(store.active("policy_2026")) == 1


def test_a_forgotten_note_stays_in_the_history(tmp_path):
    store = NoteStore(tmp_path / "m.db")
    note, _ = store.add("Тимчасово.", "lawyer", ENTITY_A, VERSION, OPEN)
    store.forget(note.id, "head")
    kept = store.get(note.id)
    assert (
        kept.status == FORGOTTEN
        and kept.closed_by == "head"
        and store.active(VERSION) == []
    )
    with pytest.raises(ValueError, match="not чинна"):
        store.forget(note.id, "head")


def test_a_note_on_a_lease_reaches_only_those_who_may_read_it(tmp_path):
    head = memory(tmp_path, "head")
    head.store.add("NDA: умови не розголошувати.", "head", ENTITY_A, VERSION, NDA)
    head.store.add("Загальна нотатка юрособи А.", "head", ENTITY_A, VERSION)
    assert [n.lease_id for n in head.notes()] == [NDA, None]
    lawyer = Memory(head.store, CLIENTS["lawyer"], get_user("lawyer"))
    assert [n.lease_id for n in lawyer.notes()] == [None]  # not the NDA one
    other = Memory(head.store, CLIENTS["lawyer_b"], get_user("lawyer_b"))
    assert other.notes() == []  # not even the general one of entity A


def test_remember_and_forget_need_the_lawyers_yes(tmp_path):
    mem = memory(tmp_path)
    keep = remember(mem, ScriptedConfirmer(False))
    args = RememberArgs(text="Для Мотор-Банку 3 % не погоджуємо.", lease_id=OPEN)
    refused = keep(args)
    assert not refused.changed and refused.confirmed is False and mem.store.all() == []
    confirm = ScriptedConfirmer(True)
    kept = remember(mem, confirm)(args)
    assert kept.changed and kept.note_id == "N-0001" and "Зберегти" in confirm.asked[0]
    notes = recall_notes(mem)(RecallArgs(lease_id=OPEN)).notes
    assert [n.text for n in notes] == ["Для Мотор-Банку 3 % не погоджуємо."]
    assert not forget(mem, ScriptedConfirmer(False))(
        ForgetArgs(note_id="N-0001")
    ).changed
    assert forget(mem, ScriptedConfirmer(True))(ForgetArgs(note_id="N-0001")).changed
    assert recall_notes(mem)(RecallArgs()).notes == []


def test_the_confirmation_shows_the_note_a_new_one_replaces(tmp_path):
    mem = memory(tmp_path)
    args = {"lease_id": OPEN, "topic": "indexation_limited"}
    remember(mem, ScriptedConfirmer(True))(
        RememberArgs(text="3 % не погоджуємо.", **args)
    )
    confirm = ScriptedConfirmer(True)
    result = remember(mem, confirm)(
        RememberArgs(text="І 5 % теж не погоджуємо.", **args)
    )
    assert result.replaces == "N-0001" and "Замінить нотатку N-0001" in confirm.asked[0]


def test_no_note_about_a_closed_lease_is_kept_or_forgotten(tmp_path):
    lawyer = memory(tmp_path)
    with pytest.raises(AccessDenied):
        remember(lawyer, ScriptedConfirmer(True))(
            RememberArgs(text="Спроба записати.", lease_id=NDA)
        )
    lawyer.store.add("NDA: умови не розголошувати.", "head", ENTITY_A, VERSION, NDA)
    confirm = ScriptedConfirmer(True)
    with pytest.raises(ToolError, match="No note N-0001"):
        forget(lawyer, confirm)(ForgetArgs(note_id="N-0001"))
    assert confirm.asked == []  # not even asked


def test_the_note_schema_goes_to_the_model_as_json():
    assert json.loads(RecallArgs(lease_id=OPEN).model_dump_json())["lease_id"] == OPEN


def test_a_note_about_a_lease_gone_from_the_registry_is_left_out(tmp_path):
    mem = memory(tmp_path)
    mem.store.add(
        "Про договір, якого вже немає.", "lawyer", ENTITY_A, VERSION, "lease_99999"
    )
    mem.store.add("Звичайна нотатка.", "lawyer", ENTITY_A, VERSION, OPEN)
    notes = recall_notes(mem)(RecallArgs()).notes
    assert [n.lease_id for n in notes] == [OPEN]
    with pytest.raises(ToolError, match="No lease lease_99999"):
        remember(mem, ScriptedConfirmer(True))(
            RememberArgs(text="Ще одна про нього.", lease_id="lease_99999")
        )


def test_a_note_already_kept_is_not_asked_about_again(tmp_path):
    mem = memory(tmp_path)
    args = RememberArgs(text="Для Мотор-Банку 3 % не погоджуємо.", lease_id=OPEN)
    remember(mem, ScriptedConfirmer(True))(args)
    confirm = ScriptedConfirmer(True)
    result = remember(mem, confirm)(args)
    assert not result.changed and result.note_id == "N-0001" and confirm.asked == []


def test_each_lease_is_asked_about_once_per_call(tmp_path):
    asked = []

    class Counting(RegistryClient):
        def summary(self, lease_id):
            asked.append(lease_id)
            return super().summary(lease_id)

    client = Counting(build_server(get_user("lawyer")), user="lawyer")
    mem = Memory(NoteStore(tmp_path / "m.db"), client, get_user("lawyer"))
    for topic in ("indexation_limited", "tenant_break_option", "landlord_repairs"):
        mem.store.add(f"Нотатка про {topic}.", "lawyer", ENTITY_A, VERSION, OPEN, topic)
    assert len(mem.notes()) == 3 and asked == [OPEN]
