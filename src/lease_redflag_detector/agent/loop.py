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
timed-out tool keeps running in the background; its result is dropped.

Time works the same way: a model call with tools gets the time left minus the reserve
for the answer, and if it runs out, the next call is the final one with the reserve.
A request runs over its timeout only if the final call itself needs the whole reserve
after an earlier step overran.
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

# Shown to the lawyer when the model gave no answer at all.
NO_ANSWER = "Запит не завершено ({reason}), відповіді немає. Спробуйте звузити питання."


class Limits(BaseModel):
    max_steps: int = 8  # model calls per request, the final answer included
    max_usd: float = 0.05
    tool_timeout_s: float = 20
    request_timeout_s: float = 120
    reserve_s: float = 15  # time kept for the final answer


class AgentConfig(BaseModel):
    """Model, prompts and limits of the agent, loaded from `configs/agent-*.toml`."""

    name: str
    model: str
    prompt: str  # the system prompt
    stop_prompt: str
    extraction: str  # config of the stage 1 extractor
    redline: str  # config of the stage 2 redline generator
    max_tokens: int = 4000
    timeout_s: float = 60
    max_retries: int = 2
    limits: Limits = Limits()
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
        self.name = config.model
        self.config = config
        self.client = anthropic.Anthropic(
            timeout=config.timeout_s, max_retries=config.max_retries
        )

    def call(self, system, messages, tools, final_only, timeout) -> Reply:
        extra = {}
        if tools:
            # The history may hold tool calls, so the tools stay defined even when
            # none may be chosen.
            extra["tools"] = tools
            extra["tool_choice"] = {"type": "none" if final_only else "auto"}
        if self.config.sampling:
            extra["output_config"] = self.config.sampling
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=system,
            messages=messages,
            timeout=min(timeout, self.config.timeout_s),
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
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.model = model
        self.tools = tools
        self.system = system
        self.limits = limits
        self.stop_prompt = stop_prompt
        self.clock = clock

    @classmethod
    def from_config(cls, config: AgentConfig, tools: Toolbox) -> "Agent":
        return cls(
            AnthropicModel(config),
            tools,
            load_prompt(config.prompt),
            config.limits,
            load_prompt(config.stop_prompt),
        )

    def run(self, question: str, trace: Trace | None = None) -> Answer:
        trace = trace or Trace()
        start = self.clock()
        deadline = start + self.limits.request_timeout_s
        trace.add(
            "request",
            question=question,
            model=self.model.name,
            limits=self.limits.model_dump(),
        )
        messages = [{"role": "user", "content": question}]
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
                    self.system,
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
                        f"Not run: {LIMIT_NAMES[skipped]} was reached.", True
                    )
                    began = self.clock()
                else:
                    began = self.clock()
                    result = self.execute(
                        call, deadline - began - self.limits.reserve_s
                    )
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

    def execute(self, call: ToolCall, timeout: float) -> ToolResult:
        own = self.tools.timeout_s(call.name) or self.limits.tool_timeout_s
        timeout = min(own, timeout)
        try:
            return call_with_timeout(lambda: self.tools.execute(call), timeout)
        except TimeoutError:
            return ToolResult(
                f"Tool {call.name} timed out after {timeout:.0f} s.", True
            )
        except Exception as e:  # noqa: BLE001 - the model gets the error, the loop goes on
            return ToolResult(f"Tool {call.name} failed: {type(e).__name__}: {e}", True)
