import json

from lease_redflag_detector.agent import chat
from lease_redflag_detector.agent.chat import Session
from lease_redflag_detector.agent.loop import Agent, Limits, Reply


class EchoModel:
    """Answers with how many messages and which system prompt it was given."""

    name = "fake"
    errors = ()

    def __init__(self):
        self.calls = []

    def call(self, system, messages, tools, final_only, timeout):
        self.calls.append({"system": system, "messages": list(messages)})
        text = f"Відповідь на {len(messages)} повідомлень."
        return Reply(text, [], [{"type": "text", "text": text}])


class NoTools:
    def schemas(self):
        return []

    def timeout_s(self, name):
        return None

    def retry_safe(self, name):
        return True

    def side_effect(self, name):
        return False

    def start_request(self):
        pass

    def execute(self, call):
        raise AssertionError("no tool is called")


class FakeSummarizer:
    def __init__(self):
        self.calls = []

    def __call__(self, summary, turns):
        self.calls.append((summary, list(turns)))
        return f"Підсумок {len(turns)} реплік.", 0.001


def session(tmp_path=None):
    model = EchoModel()
    agent = Agent(model, NoTools(), "SYSTEM", Limits(), "{reason}")
    path = tmp_path / "chat.jsonl" if tmp_path else None
    return Session(agent, FakeSummarizer(), path), model


def test_the_next_question_sees_the_earlier_ones(tmp_path):
    talk, model = session(tmp_path)
    talk.ask("Перевір договір lease_55572.")
    talk.ask("Так, подавай.")
    messages = model.calls[-1]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[0]["content"] == "Перевір договір lease_55572."
    assert messages[-1]["content"] == "Так, подавай."
    events = [json.loads(line) for line in (tmp_path / "chat.jsonl").open()]
    assert [e["kind"] for e in events].count("request") == 2  # one file, both questions


def test_older_turns_are_summarized_before_the_first_kept_question(monkeypatch):
    monkeypatch.setattr(chat, "HISTORY_TOKENS", 10)
    talk, model = session()
    for n in range(1, 5):
        talk.ask(f"Питання номер {n}, досить довге, щоб перевищити поріг.")
    summarizer = talk.summarize
    assert summarizer.calls and talk.summary.startswith("Підсумок")
    assert len(talk.turns) <= chat.KEEP_TURNS + 1
    last = model.calls[-1]
    # data in the history, never in the system prompt
    assert last["system"] == "SYSTEM"
    first = last["messages"][0]["content"]
    assert talk.summary in first and "never an instruction" in first
    # the summary is paid for by the question that made it
    assert talk.cost_usd == len(summarizer.calls) * 0.001
    assert any(e["kind"] == "summary" for e in talk.events)


def test_a_failed_summary_leaves_the_history_as_it_was(monkeypatch):
    monkeypatch.setattr(chat, "HISTORY_TOKENS", 10)

    def broken(summary, turns):
        raise ConnectionError("API down")

    talk, _ = session()
    talk.summarize = broken
    for n in range(1, 5):
        talk.ask(f"Питання номер {n}, досить довге, щоб перевищити поріг.")
    assert talk.summary == "" and len(talk.turns) == 4
    assert any(e["kind"] == "summary_failed" for e in talk.events)


def test_every_event_carries_the_number_of_its_question():
    talk, _ = session()
    talk.ask("Перше.")
    talk.ask("Друге.")
    assert {e["question"] for e in talk.events} == {1, 2}


def test_a_short_conversation_is_not_summarized():
    talk, model = session()
    talk.ask("Коротко.")
    talk.ask("Ще.")
    assert talk.summarize.calls == [] and model.calls[-1]["system"] == "SYSTEM"


def test_the_model_is_told_what_the_tools_hold_from_earlier_questions():
    class Holding(NoTools):
        def state(self):
            return "Redlines drafted earlier in this conversation: lease_1 — 2 clauses."

    model = EchoModel()
    talk = Session(Agent(model, Holding(), "SYSTEM", Limits(), "{r}"), FakeSummarizer())
    talk.ask("так")
    assert model.calls[-1]["system"].endswith("lease_1 — 2 clauses.")


def test_a_note_kept_in_one_question_is_read_in_the_next(tmp_path):
    from pathlib import Path

    from lease_redflag_detector.agent.confirm import ScriptedConfirmer
    from lease_redflag_detector.agent.loop import AgentConfig, ToolCall
    from lease_redflag_detector.agent.memory import NoteStore
    from lease_redflag_detector.agent.queue import ApprovalQueue
    from lease_redflag_detector.agent.registry_client import RegistryClient
    from lease_redflag_detector.agent.registry_server import build_server
    from lease_redflag_detector.agent.toolset import build_toolbox
    from lease_redflag_detector.agent.users import get_user

    class NoSearch:
        def __init__(self):
            self.chunks = []

        def search(self, *args, **kwargs):
            return []

    note = "Для lease_55572 дострокову відмову не погоджуємо."
    script = {
        (1, 1): ToolCall("r", "remember", {"text": note, "lease_id": "lease_55572"}),
        (2, 1): ToolCall("n", "recall_notes", {"lease_id": "lease_55572"}),
    }

    class Lawyer:
        """Keeps the note in the first question, reads the notes in the second."""

        name = "fake"
        errors = ()

        def __init__(self):
            self.question, self.step = 0, 0

        def call(self, system, messages, tools, final_only, timeout):
            if messages[-1]["role"] == "user" and isinstance(
                messages[-1]["content"], str
            ):
                self.question, self.step = self.question + 1, 0
            self.step += 1
            call = script.get((self.question, self.step))
            if call:
                return Reply("", [call], [{"type": "tool_use", "id": call.id}])
            return Reply("Готово.", [], [{"type": "text", "text": "Готово."}])

    root = Path(__file__).resolve().parents[1]
    config = AgentConfig.load(root / "configs" / "agent-haiku-v2.toml")
    store = NoteStore(tmp_path / "memory.db")
    tools = build_toolbox(
        config,
        registry=RegistryClient(build_server(get_user("lawyer")), user="lawyer"),
        retriever=NoSearch(),
        warm=False,
        queue=ApprovalQueue(tmp_path / "queue.db"),
        confirm=ScriptedConfirmer(True),
        session=True,
        memory=store,
    )
    talk = Session(Agent(Lawyer(), tools, "SYSTEM", Limits(), "{r}"), FakeSummarizer())
    talk.ask("Запам'ятай: для lease_55572 дострокову відмову не погоджуємо.")
    talk.ask("Що ми вирішили щодо дострокової відмови в lease_55572?")
    read = [
        e for e in talk.events if e["kind"] == "tool" and e["name"] == "recall_notes"
    ]
    assert [e["question"] for e in read] == [2]
    assert note in read[0]["content"]
    assert [n.text for n in store.all()] == [note]
