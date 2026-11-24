import json

import pytest
from pydantic import BaseModel

from lease_redflag_detector.agent.faults import FaultyToolbox, parse
from lease_redflag_detector.agent.loop import (
    Agent,
    Limits,
    Reply,
    Retries,
    StopReason,
    ToolCall,
)
from lease_redflag_detector.agent.tools import (
    Tool,
    Toolbox,
    ToolError,
    TransientError,
    api_failure,
)


class Args(BaseModel):
    query: str


class Found(BaseModel):
    fragments: list[str]


def search(args: Args) -> Found:
    return Found(fragments=[f"fragment on {args.query}"])


def toolbox(fn=search, **flags) -> Toolbox:
    return Toolbox(
        [Tool("search_corpus", "tools/search_corpus_v1", Args, Found, fn, **flags)]
    )


class Model:
    """Asks for one search, then answers with the text of the tool result."""

    name = "fake"
    errors = ()

    def __init__(self):
        self.results = []

    def call(self, system, messages, tools, final_only, timeout):
        if len(messages) == 1:
            call = ToolCall("t1", "search_corpus", {"query": "поступки"})
            return Reply("", [call], [{"type": "tool_use", "id": "t1"}])
        result = messages[-1]["content"][0]
        self.results.append(result)
        return Reply("Відповідь.", [], [{"type": "text", "text": "Відповідь."}])


def run(tools, **limits):
    sleeps = []
    model = Model()
    agent = Agent(
        model,
        tools,
        "system",
        Limits(**limits),
        "STOP {reason}",
        Retries(max_attempts=3, backoff_s=1.0, max_backoff_s=8.0),
        sleep=sleeps.append,
    )
    answer = agent.run("Хто погоджує поступки?")
    return answer, model.results[0], answer.trace.tool_calls()[0], sleeps


def test_fault_specs_are_parsed_and_checked():
    faults = parse("503, search_corpus:timeout*2,get_lease:schema")
    assert [(f.tool, f.kind, f.times) for f in faults] == [
        (None, "503", None),
        ("search_corpus", "timeout", 2),
        ("get_lease", "schema", None),
    ]
    with pytest.raises(ValueError, match="unknown fault"):
        parse("search_corpus:500")
    with pytest.raises(ValueError, match="no such tools"):
        FaultyToolbox(toolbox(), "find_lease:503")


def test_a_service_that_comes_back_is_retried_with_backoff():
    answer, result, event, sleeps = run(FaultyToolbox(toolbox(), "search_corpus:503*2"))
    assert not result["is_error"] and "fragment on поступки" in result["content"]
    assert event["attempts"] == 3 and event["error_kind"] is None
    assert sleeps == [1.0, 2.0]
    retries = [e for e in answer.trace.events if e["kind"] == "tool_retry"]
    assert [r["attempt"] for r in retries] == [1, 2]
    assert answer.trace.events[0]["faults"] == "search_corpus:503*2"


def test_a_service_that_stays_down_is_reported_as_unavailable():
    answer, result, event, _sleeps = run(FaultyToolbox(toolbox(), "503"))
    assert result["is_error"] and "search_corpus is unavailable" in result["content"]
    assert "Attempts: 3; it cannot be retried" in result["content"]
    assert event["attempts"] == 3 and event["error_kind"] == "transient"
    assert answer.stop_reason == StopReason.FINAL


def test_a_rate_limit_waits_as_long_as_the_service_asks():
    _, _, event, sleeps = run(FaultyToolbox(toolbox(), "429*1"))
    assert event["attempts"] == 2 and sleeps == [1.0]


def test_a_timeout_is_retried_too():
    _, result, event, _ = run(FaultyToolbox(toolbox(), "timeout"))
    assert event["error_kind"] == "timeout" and event["attempts"] == 3
    assert "timed out" in result["content"]


def test_a_changed_result_format_is_a_schema_error_in_the_trace_and_not_retried():
    _, result, event, sleeps = run(FaultyToolbox(toolbox(), "schema"))
    assert event["error_kind"] == "schema" and event["attempts"] == 1 and sleeps == []
    assert "unexpected format: fragments: Field required" in result["content"]


def test_a_tool_with_a_side_effect_or_not_retry_safe_is_never_repeated():
    for flags in ({"side_effect": True}, {"retry_safe": False}):
        _, result, event, sleeps = run(FaultyToolbox(toolbox(**flags), "503"))
        assert event["attempts"] == 1 and sleeps == []
        assert "unavailable" not in result["content"]


def test_expected_tool_errors_are_not_retried():
    def no_lease(args):
        raise ToolError("No lease lease_1 in the registry.")

    _, _result, event, sleeps = run(toolbox(no_lease))
    assert event["error_kind"] == "tool_error" and event["attempts"] == 1
    assert sleeps == []


def test_retries_stop_when_the_request_has_no_time_left():
    _, result, event, sleeps = run(
        FaultyToolbox(toolbox(), "503"), request_timeout_s=2.4, reserve_s=1.5
    )
    assert event["attempts"] == 1 and sleeps == []
    assert "Attempts: 1" in result["content"]


def test_transient_errors_of_the_api_inside_a_tool_are_retried():
    assert isinstance(
        api_failure("Extraction failed", "RateLimitError: 429", 0.0), TransientError
    )
    assert isinstance(
        api_failure("Extraction failed", "OverloadedError: 529", 0.0), TransientError
    )
    error = api_failure("Extraction failed", "BadRequestError: 400", 0.001)
    assert not isinstance(error, TransientError) and error.cost_usd == 0.001

    def overloaded(args):
        raise api_failure("No valid redline", "OverloadedError: overloaded", 0.0)

    _, _, event, sleeps = run(toolbox(overloaded))
    assert event["attempts"] == 3 and sleeps == [1.0, 2.0]


def test_the_cost_of_every_attempt_counts():
    def costly_failure(args):
        raise TransientError("503", cost_usd=0.001)

    answer, _, event, _ = run(toolbox(costly_failure))
    assert event["cost_usd"] == pytest.approx(0.003)
    assert answer.cost_usd == pytest.approx(0.003)
    assert json.loads(json.dumps(event))  # the trace event stays plain JSON


def test_a_service_asking_for_a_longer_pause_than_allowed_is_not_retried_early():
    def rate_limited(args):
        raise TransientError("429 Too Many Requests", retry_after=30)

    _, result, event, sleeps = run(toolbox(rate_limited))
    assert event["attempts"] == 1 and sleeps == []
    assert "search_corpus is unavailable" in result["content"]


def test_rules_for_a_tool_replace_the_general_ones():
    tools = Toolbox(
        [
            Tool("search_corpus", "tools/search_corpus_v1", Args, Found, search),
            Tool("get_lease", "tools/get_lease_v1", Args, Found, search),
        ]
    )
    faulty = FaultyToolbox(tools, "503,search_corpus:schema*1")
    call = ToolCall("t", "search_corpus", {"query": "q"})
    assert faulty.execute(call).error_kind == "schema"
    assert faulty.execute(call).error_kind is None
    other = ToolCall("t", "get_lease", {"query": "q"})
    assert faulty.execute(other).error_kind == "transient"
