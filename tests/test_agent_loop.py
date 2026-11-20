import time
from pathlib import Path

from lease_redflag_detector.agent.loop import (
    LIMIT_NAMES,
    NO_ANSWER,
    Agent,
    AgentConfig,
    Limits,
    Reply,
    StopReason,
    ToolCall,
    ToolResult,
)
from lease_redflag_detector.agent.trace import Trace
from lease_redflag_detector.extraction.extractor import load_prompt

ROOT = Path(__file__).resolve().parents[1]

STOP = "STOP: {reason}"


def search(n: int = 1) -> Reply:
    call = ToolCall(f"t{n}", "search", {"query": f"q{n}"})
    return Reply("", [call], [{"type": "tool_use", "id": call.id}])


def final(text: str = "Відповідь.") -> Reply:
    return Reply(text, [], [{"type": "text", "text": text}])


class ScriptedModel:
    """Replies from a list (the last one repeats) or from a function of the call."""

    errors = (ConnectionError,)

    def __init__(self, replies, name="fake", tokens=(0, 0), clock=None, seconds=0.0):
        self.replies = replies
        self.name = name
        self.tokens = tokens
        self.clock = clock
        self.seconds = seconds
        self.calls = []

    def call(self, system, messages, tools, final_only, timeout):
        self.calls.append(
            {"messages": [dict(m) for m in messages], "final_only": final_only}
        )
        if self.clock:
            self.clock.now += self.seconds
        if callable(self.replies):
            reply = self.replies(len(self.calls), final_only)
        else:
            reply = self.replies[min(len(self.calls), len(self.replies)) - 1]
        reply.input_tokens, reply.output_tokens = self.tokens
        return reply


class Tools:
    def __init__(self, run=None, cost=0.0):
        self.run = run or (lambda call: f"result of {call.args['query']}")
        self.cost = cost
        self.calls = []

    def schemas(self):
        return [{"name": "search"}]

    def timeout_s(self, name):
        return None

    def retry_safe(self, name):
        return True

    def execute(self, call):
        self.calls.append(call)
        return ToolResult(self.run(call), cost_usd=self.cost)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def agent(model, tools=None, clock=time.monotonic, sleeps=None, **limits):
    return Agent(
        model,
        tools or Tools(),
        "system",
        Limits(**limits),
        STOP,
        clock=clock,
        sleep=(sleeps.append if sleeps is not None else lambda s: None),
    )


def until_final_only(step, final_only):
    return final("Частковий результат.") if final_only else search(step)


def test_answer_without_tools_stops_at_the_first_step():
    tools = Tools()
    answer = agent(ScriptedModel([final()]), tools).run("Що таке гарантійний платіж?")
    assert answer.stop_reason == StopReason.FINAL and answer.steps == 1
    assert answer.text == "Відповідь." and tools.calls == []
    assert [e["kind"] for e in answer.trace.events] == ["request", "model", "stop"]


def test_tool_result_goes_back_to_the_model():
    model = ScriptedModel([search(), final()])
    answer = agent(model).run("питання")
    assert answer.stop_reason == StopReason.FINAL and answer.steps == 2
    tool_result = model.calls[1]["messages"][-1]["content"][0]
    assert tool_result == {
        "type": "tool_result",
        "tool_use_id": "t1",
        "content": "result of q1",
        "is_error": False,
    }


def test_a_model_that_never_stops_gets_a_final_call_at_the_step_limit():
    model = ScriptedModel(until_final_only)
    tools = Tools()
    answer = agent(model, tools, max_steps=8).run("питання без відповіді")
    assert answer.stop_reason == StopReason.MAX_STEPS and answer.steps == 8
    assert len(tools.calls) == 7 and answer.text == "Частковий результат."
    assert [c["final_only"] for c in model.calls] == [False] * 7 + [True]
    last_message = model.calls[-1]["messages"][-1]["content"]
    assert last_message[-1] == {"type": "text", "text": "STOP: the step limit"}


def test_the_budget_stops_before_it_is_spent_and_leaves_the_final_answer():
    # 100k input tokens of Haiku cost $0.01 per call.
    model = ScriptedModel(
        until_final_only, name="claude-haiku-5-5", tokens=(100_000, 0)
    )
    answer = agent(model, max_usd=0.05).run("перевір усі договори")
    assert answer.stop_reason == StopReason.BUDGET
    assert answer.cost_usd <= 0.05 + 1e-9
    assert model.calls[-1]["final_only"] and answer.text == "Частковий результат."


def test_the_cost_of_model_calls_inside_tools_counts_towards_the_budget():
    tools = Tools(cost=0.02)
    answer = agent(ScriptedModel(until_final_only), tools, max_usd=0.05).run(
        "перевір усі"
    )
    assert answer.stop_reason == StopReason.BUDGET
    assert len(tools.calls) == 3  # $0.06 > $0.05 after the third call


def test_tool_calls_left_after_the_budget_get_a_result_but_do_not_run():
    reply = Reply(
        "", [ToolCall(f"t{i}", "search", {"query": str(i)}) for i in range(3)], []
    )
    tools = Tools(cost=0.03)
    model = ScriptedModel(lambda step, final_only: final() if final_only else reply)
    answer = agent(model, tools, max_usd=0.05).run("перевір усі")
    assert len(tools.calls) == 2  # the second one starts within the budget
    results = model.calls[-1]["messages"][-1]["content"]
    assert results[2]["is_error"] and "budget" in results[2]["content"]
    assert answer.stop_reason == StopReason.BUDGET


def test_a_slow_tool_times_out_and_the_model_gets_the_error():
    def slow(call):
        time.sleep(1)
        return "too late"

    model = ScriptedModel([search(), final("Пошук не відповів.")])
    answer = agent(model, Tools(slow), tool_timeout_s=0.1).run("питання")
    result = model.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "timed out" in result["content"]
    assert answer.stop_reason == StopReason.FINAL
    assert answer.trace.tool_calls()[0]["is_error"]


def test_a_failing_tool_does_not_stop_the_loop():
    def broken(call):
        raise KeyError("results")

    model = ScriptedModel([search(), final()])
    answer = agent(model, Tools(broken)).run("питання")
    result = model.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "KeyError" in result["content"]
    assert answer.stop_reason == StopReason.FINAL


def test_the_request_timeout_keeps_time_for_the_final_answer():
    clock = Clock()
    model = ScriptedModel(until_final_only, clock=clock, seconds=30)
    tools = Tools()
    answer = agent(model, tools, clock=clock, request_timeout_s=120, reserve_s=15).run(
        "q"
    )
    # 30 s per call: the fourth call ends at 120 s, its search is not run, the fifth
    # answers within the reserve.
    assert answer.stop_reason == StopReason.TIMEOUT and answer.steps == 5
    assert len(tools.calls) == 3
    assert model.calls[-1]["final_only"] and answer.text == "Частковий результат."


def test_a_model_call_that_hangs_leaves_the_reserve_for_the_answer():
    def hangs_once(step, final_only):
        if step == 1:
            time.sleep(1)
        return final("Не встиг.")

    model = ScriptedModel(hangs_once)
    answer = agent(model, request_timeout_s=0.5, reserve_s=0.2).run("питання")
    assert answer.stop_reason == StopReason.TIMEOUT and answer.text == "Не встиг."
    assert model.calls[-1]["final_only"]


def test_a_model_that_always_hangs_ends_the_request_with_a_timeout():
    def hangs(step, final_only):
        time.sleep(1)
        return final()

    answer = agent(ScriptedModel(hangs), request_timeout_s=0.2, reserve_s=0.05).run("q")
    assert answer.stop_reason == StopReason.TIMEOUT
    assert answer.text == NO_ANSWER.format(reason="timeout")


def test_a_model_error_ends_the_request_without_crashing():
    def down(step, final_only):
        raise ConnectionError("503")

    answer = agent(ScriptedModel(down)).run("питання")
    assert answer.stop_reason == StopReason.MODEL_ERROR
    assert answer.trace.events[-2]["kind"] == "model_error"


def test_the_trace_is_written_as_json_lines(tmp_path):
    path = tmp_path / "trace.jsonl"
    agent(ScriptedModel([search(), final()])).run("питання", Trace(path))
    kinds = [
        line.split('"kind": "')[1].split('"')[0]
        for line in path.read_text().splitlines()
    ]
    assert kinds == ["request", "model", "tool", "model", "stop"]


def test_agent_configs_and_their_prompts_load():
    for path in (ROOT / "configs").glob("agent-*.toml"):
        config = AgentConfig.load(path)
        assert config.name == path.stem
        assert load_prompt(config.prompt)
        for reason in LIMIT_NAMES.values():
            assert reason in load_prompt(config.stop_prompt).format(reason=reason)
