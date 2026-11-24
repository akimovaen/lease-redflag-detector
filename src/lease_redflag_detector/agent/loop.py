"""The agent loop: the model answers or asks for tools, the code runs them, repeat.

The model decides which tools to call and when to answer; the code only runs the
calls and keeps the request within its limits (`Limits`): steps, dollars, and time per
tool call and per request. A limit is checked before each model call, not after, so
the last call is always left for the answer: when a limit is near, the model gets the
stop prompt and a call in which no tool can be chosen, and answers with what it has.
The request then stops with that limit as its reason, not silently.

The budget counts every model call, including those a tool makes itself (a tool
reports its own cost). The next call is estimated to cost at least as much as the
last one, since the history only grows; a call with tools runs only if the answer
after it still fits. A tool's own cost is known only after it runs, so a request may
go over its budget by one tool call and the final answer.

A failing tool never stops the loop: an exception or a timeout goes back to the model
as text, and the model decides what to do next. Python cannot kill a thread, so a
timed-out tool keeps running in the background; its result is dropped. A tool with a
side effect therefore runs in the loop's own thread with no time limit of its own: it
must not act after the model was told it had not, and it asks the lawyer to confirm.

Every failed tool call has a kind (`ToolResult.error_kind`). Only a transient failure
(a timeout, 429, 503) of a tool marked `retry_safe` is repeated, with exponential
backoff or the pause the service asked for, and only while the time and budget of the
request leave room for it. A wrong result format, invalid arguments or an expected
error would fail the same way again, and a tool with a side effect could act twice.
When the retries run out, or the time, budget or the pause the service asks for leave
no room for another one, the model is told the tool is unavailable; what to do then is
in the system prompt. Every retry is in the trace.

Time works the same way: a model call with tools gets the time left minus the reserve
for the answer, and if it runs out, the next call is the final one with the reserve.
A request runs over its timeout only if the final call itself needs the whole reserve
after an earlier step overran. The API client repeats a failed model call only as many
times as fit in that call's time: a repeat that outlived it would still be paid for,
unseen by the budget.

A model without a price is refused (`require_price`): its calls would cost nothing to
the budget, and the budget limit would never stop a request.
"""

import threading
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Protocol

import anthropic
from pydantic import BaseModel

from lease_redflag_detector.agent.trace import Trace
from lease_redflag_detector.extraction.extractor import load_prompt
from lease_redflag_detector.extraction.metrics import cost_usd


class StopReason(StrEnum):
    FINAL = "final"
    MAX_STEPS = "max_steps"
    BUDGET = "budget"
    TIMEOUT = "timeout"
    MODEL_ERROR = "model_error"


# How the stop prompt names each limit.
LIMIT_NAMES = {
    StopReason.MAX_STEPS: "the step limit",
    StopReason.BUDGET: "the budget",
    StopReason.TIMEOUT: "the time limit",
}

# Kinds of tool failure that may pass if the call is repeated.
RETRYABLE = {"transient", "timeout"}
UNAVAILABLE = (
    "{name} is unavailable: {error} Attempts: {attempts}; it cannot be retried within "
    "this request."
)

# Shown to the lawyer when the model gave no answer at all.
NO_ANSWER = "Запит не завершено ({reason}), відповіді немає. Спробуйте звузити питання."
# The longest pause of the API client between two attempts (anthropic MAX_RETRY_DELAY).
CLIENT_BACKOFF_S = 8.0


def require_price(model: str) -> None:
    if cost_usd(model, 0, 0) is None:
        raise ValueError(
            f"No price for {model} in extraction/metrics.py: its calls would not "
            "count toward the budget of a request."
        )


def client_retries(timeout: float, attempt_s: float, max_retries: int) -> int:
    """How many repeats of a model call of `attempt_s` seconds fit in `timeout`, with
    the client's longest pause before each."""
    fit = int((timeout + CLIENT_BACKOFF_S) // (attempt_s + CLIENT_BACKOFF_S)) - 1
    return max(0, min(max_retries, fit))


class Limits(BaseModel):
    max_steps: int = 8  # model calls per request, the final answer included
    max_usd: float = 0.05
    tool_timeout_s: float = 20
    request_timeout_s: float = 120
    reserve_s: float = 15  # time kept for the final answer


class Retries(BaseModel):
    max_attempts: int = 3  # the first call included
    backoff_s: float = 1.0  # doubled after every failed attempt
    max_backoff_s: float = 8.0  # a longer pause asked by a service: no retry


class AgentConfig(BaseModel):
    """Model, prompts and limits of the agent, loaded from `configs/agent-*.toml`."""

    name: str
    model: str
    prompt: str  # the system prompt
    stop_prompt: str
    extraction: str  # config of the stage 1 extractor
    redline: str  # config of the stage 2 redline generator
    user: str = (
        "lawyer"  # who the agent works for (configs/users.toml); AS_USER= at start
    )
    max_tokens: int = 4000
    timeout_s: float = 60
    max_retries: int = 2
    limits: Limits = Limits()
    retries: Retries = Retries()
    sampling: dict[str, str | float | int] = {}

    @classmethod
    def load(cls, path: Path) -> "AgentConfig":
        return cls.model_validate(tomllib.loads(path.read_text()))


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    cost_usd: float = 0.0  # model calls the tool made itself
    # Why a call failed: transient, timeout, schema, invalid_args, tool_error, denied,
    # unknown_tool, exception, not_run; None if it did not.
    error_kind: str | None = None
    retry_after: float | None = None  # the pause a service asked for, seconds
    attempts: int = 1


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall]
    content: list[dict]  # the assistant message as sent back in the history
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None


class Model(Protocol):
    name: str
    errors: tuple[type[Exception], ...]

    def call(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        final_only: bool,
        timeout: float,
    ) -> Reply: ...


class Toolbox(Protocol):
    def schemas(self) -> list[dict]: ...

    def timeout_s(self, name: str) -> float | None: ...  # None: the default

    def retry_safe(self, name: str) -> bool: ...

    def side_effect(self, name: str) -> bool: ...

    def start_request(self) -> None: ...

    def execute(self, call: ToolCall) -> ToolResult: ...


@dataclass
class Answer:
    text: str
    stop_reason: StopReason
    steps: int
    cost_usd: float
    latency_s: float
    trace: Trace = field(repr=False)


class AnthropicModel:
    """Claude through the Anthropic API. Rate limits, server errors and timeouts of the
    model are retried by the SDK client; what is left is `errors`."""

    errors = (anthropic.APIError,)

    def __init__(self, config: AgentConfig) -> None:
        require_price(config.model)
        self.name = config.model
        self.config = config
        self.client = anthropic.Anthropic(
            timeout=config.timeout_s, max_retries=config.max_retries
        )

    def call(self, system, messages, tools, final_only, timeout) -> Reply:
        attempt_s = min(timeout, self.config.timeout_s)
        retries = client_retries(timeout, attempt_s, self.config.max_retries)
        extra = {}
        if tools:
            # The history may hold tool calls, so the tools stay defined even when
            # none may be chosen.
            extra["tools"] = tools
            extra["tool_choice"] = {"type": "none" if final_only else "auto"}
        if self.config.sampling:
            extra["output_config"] = self.config.sampling
        response = self.client.with_options(max_retries=retries).messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=system,
            messages=messages,
            timeout=attempt_s,
            **extra,
        )
        return Reply(
            text="".join(b.text for b in response.content if b.type == "text"),
            tool_calls=[
                ToolCall(b.id, b.name, b.input)
                for b in response.content
                if b.type == "tool_use"
            ],
            content=[
                b.model_dump(mode="json", exclude_none=True) for b in response.content
            ],
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )


def call_with_timeout(fn: Callable, timeout: float):
    """Run `fn` and return its result, or raise TimeoutError after `timeout` seconds."""
    box = {}

    def target():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 - re-raised in the caller's thread
            box["error"] = e

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(max(timeout, 0))
    if thread.is_alive():
        raise TimeoutError
    if "error" in box:
        raise box["error"]
    return box["value"]


def add_text(message: dict, text: str) -> None:
    """Append a text block to a user message (after its tool results, if any)."""
    content = message["content"]
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    message["content"] = [*content, {"type": "text", "text": text}]


class Agent:
    def __init__(
        self,
        model: Model,
        tools: Toolbox,
        system: str,
        limits: Limits,
        stop_prompt: str,
        retries: Retries | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        user: str | None = None,
    ) -> None:
        self.user = user  # who the agent works for, recorded in the trace
        self.model = model
        self.tools = tools
        self.system = system
        self.limits = limits
        self.stop_prompt = stop_prompt
        self.retries = retries or Retries()
        self.clock = clock
        self.sleep = sleep

    @classmethod
    def from_config(cls, config: AgentConfig, tools: Toolbox) -> "Agent":
        return cls(
            AnthropicModel(config),
            tools,
            load_prompt(config.prompt),
            config.limits,
            load_prompt(config.stop_prompt),
            config.retries,
            user=config.user,
        )

    def run(
        self,
        question: str,
        trace: Trace | None = None,
        history: list[dict] | None = None,
        context: str = "",
    ) -> Answer:
        """Answer `question`. In a conversation (`chat.py`), `history` holds the
        earlier questions and answers as messages and `context` a summary of what is
        older still, added to the system prompt; the limits apply to this question."""
        trace = trace or Trace()
        history = history or []
        start = self.clock()
        deadline = start + self.limits.request_timeout_s
        trace.add(
            "request",
            question=question,
            user=self.user,
            model=self.model.name,
            limits=self.limits.model_dump(),
            retries=self.retries.model_dump(),
            # Failures injected on purpose (faults.py), if any.
            faults=getattr(self.tools, "faults", None),
            history_messages=len(history),
            context=context or None,
        )
        self.tools.start_request()
        system = f"{self.system}\n\n{context}" if context else self.system
        messages = [*(dict(m) for m in history), {"role": "user", "content": question}]
        schemas = self.tools.schemas()
        forced: StopReason | None = None
        estimate = 0.0  # cost of the last model call

        def finish(text: str, reason: StopReason, steps: int) -> Answer:
            latency = self.clock() - start
            text = text.strip() or NO_ANSWER.format(reason=reason)
            trace.add(
                "stop",
                reason=reason,
                steps=steps,
                answer=text,
                cost_usd=round(trace.cost_usd, 6),
                latency_s=round(latency, 3),
            )
            return Answer(text, reason, steps, trace.cost_usd, latency, trace)

        for step in range(1, self.limits.max_steps + 1):
            forced = forced or self.limit(step, trace.cost_usd, estimate, deadline)
            if forced:
                add_text(
                    messages[-1], self.stop_prompt.format(reason=LIMIT_NAMES[forced])
                )
            began = self.clock()
            # A call with tools may not eat into the reserve; the final one gets it.
            if forced:
                timeout = max(deadline - began, self.limits.reserve_s)
            else:
                timeout = deadline - began - self.limits.reserve_s
            try:
                call = partial(
                    self.model.call,
                    system,
                    messages,
                    schemas,
                    bool(forced),
                    timeout,
                )
                reply = call_with_timeout(call, timeout)
            except TimeoutError:
                trace.add("model_timeout", step=step, final_only=bool(forced))
                if forced:
                    return finish("", StopReason.TIMEOUT, step)
                forced = StopReason.TIMEOUT
                continue
            except self.model.errors as e:
                trace.add("model_error", step=step, error=f"{type(e).__name__}: {e}")
                return finish("", StopReason.MODEL_ERROR, step)
            event = trace.model_call(
                step, self.model.name, reply, self.clock() - began, bool(forced)
            )
            estimate = event["cost_usd"]
            messages.append({"role": "assistant", "content": reply.content})
            if forced or not reply.tool_calls:
                return finish(reply.text, forced or StopReason.FINAL, step)

            results = []
            for call in reply.tool_calls:
                skipped = self.limit(
                    step, trace.cost_usd, estimate, deadline, tools=True
                )
                if skipped:
                    # Every tool call needs a result; the ones left are not run.
                    result = ToolResult(
                        f"Not run: {LIMIT_NAMES[skipped]} was reached.",
                        True,
                        error_kind="not_run",
                    )
                    began = self.clock()
                else:
                    began = self.clock()
                    result = self.execute(call, deadline, step, trace, estimate)
                trace.tool_call(step, call, result, self.clock() - began)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                )
            messages.append({"role": "user", "content": results})
        raise AssertionError("the last step always answers")  # pragma: no cover

    def limit(
        self,
        step: int,
        spent: float,
        estimate: float,
        deadline: float,
        tools: bool = False,
    ) -> StopReason | None:
        """The limit that ends the request before this step, if any. With `tools`, it is
        checked before a tool call, which leaves the next model call for the answer."""
        if deadline - self.clock() <= self.limits.reserve_s:
            return StopReason.TIMEOUT
        if spent + (1 if tools else 2) * estimate > self.limits.max_usd:
            return StopReason.BUDGET
        if not tools and step >= self.limits.max_steps:
            return StopReason.MAX_STEPS
        return None

    def execute(
        self, call: ToolCall, deadline: float, step: int, trace: Trace, estimate: float
    ) -> ToolResult:
        """Run a tool call, repeating a transient failure of a retry-safe tool while the
        time and budget of the request allow; the result carries the cost of every
        attempt."""
        cost = 0.0
        for attempt in range(1, self.retries.max_attempts + 1):
            result = self.attempt(call, deadline - self.clock() - self.limits.reserve_s)
            cost += result.cost_usd
            result.cost_usd, result.attempts = cost, attempt
            if result.error_kind not in RETRYABLE or not self.tools.retry_safe(
                call.name
            ):
                return result
            if attempt == self.retries.max_attempts:
                break
            pause = (
                result.retry_after
                if result.retry_after is not None
                else min(
                    self.retries.backoff_s * 2 ** (attempt - 1),
                    self.retries.max_backoff_s,
                )
            )
            # A service that asks for a longer pause than allowed would refuse an
            # earlier retry too.
            if pause > self.retries.max_backoff_s:
                break
            no_time = deadline - self.clock() - pause <= self.limits.reserve_s
            no_money = trace.cost_usd + cost + estimate > self.limits.max_usd
            if no_time or no_money:
                break
            trace.add(
                "tool_retry",
                step=step,
                name=call.name,
                attempt=attempt,
                error=result.content,
                pause_s=pause,
            )
            self.sleep(pause)
        result.content = UNAVAILABLE.format(
            name=call.name, error=result.content, attempts=result.attempts
        )
        return result

    def attempt(self, call: ToolCall, timeout: float) -> ToolResult:
        own = self.tools.timeout_s(call.name) or self.limits.tool_timeout_s
        timeout = min(own, timeout)
        try:
            if self.tools.side_effect(call.name):
                # In this thread and without a time limit: a timed-out thread would
                # still act after the model was told it had not, and the lawyer's
                # confirmation is asked here.
                return self.tools.execute(call)
            return call_with_timeout(lambda: self.tools.execute(call), timeout)
        except TimeoutError:
            return ToolResult(
                f"Tool {call.name} timed out after {timeout:.0f} s.",
                True,
                error_kind="timeout",
            )
        except Exception as e:  # noqa: BLE001 - the model gets the error, the loop goes on
            return ToolResult(
                f"Tool {call.name} failed: {type(e).__name__}: {e}",
                True,
                error_kind="exception",
            )
