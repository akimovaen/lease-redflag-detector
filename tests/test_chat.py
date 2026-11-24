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
