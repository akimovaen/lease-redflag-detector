"""Failures of the tools, injected on purpose to check how the agent handles them.

    FAULTS=503                    every call of every tool answers 503
    FAULTS=search_corpus:timeout  only the search times out
    FAULTS=search_corpus:503*2    the first two calls of the search answer 503
    FAULTS=find_leases:schema     the result comes with a renamed field
    FAULTS=429,get_lease:schema   several at once

- timeout: the call fails as if its time limit had passed. It fails at once instead
  of waiting, so that a task with retries does not take minutes; the real timeout of a
  hanging tool is covered by the tests of the loop.
- 429 and 503: a rate limit (with a one-second retry-after) and an unavailable service.
- schema: the tool runs, and the first field of its result is renamed, as a provider
  might do without warning; the result then fails its schema.
- lost: the tool runs and acts, and its answer is lost on the way back, as with a
  dropped connection: the model sees a transient error and may call again, which must
  not act twice.

`*N` limits a rule to the first N calls of the tool, retries included, so that a task
can show a service that comes back after a retry. The rules named for a tool replace
the general ones for that tool: with `503,search_corpus:schema*1` the first search gets
the schema fault and the later ones none, while every other tool answers 503.

The wrapper has the interface of a `Toolbox` and is used by `make agent FAULTS=...`
and by the evals.
"""

from collections import Counter
from dataclasses import dataclass

from lease_redflag_detector.agent.loop import ToolCall, ToolResult
from lease_redflag_detector.agent.tools import Toolbox

KINDS = ("timeout", "429", "503", "schema", "lost")
RETRY_AFTER_S = 1.0


@dataclass(frozen=True)
class Fault:
    tool: str | None  # None: every tool
    kind: str
    times: int | None  # None: every call


def parse(spec: str) -> list[Fault]:
    faults = []
    for item in filter(None, (part.strip() for part in spec.split(","))):
        tool, _, rest = item.rpartition(":")
        kind, _, times = rest.partition("*")
        if kind not in KINDS:
            raise ValueError(f"unknown fault {kind!r} in {item!r}; one of {KINDS}")
        if times and not times.isdigit():
            raise ValueError(f"not a number of calls: {times!r} in {item!r}")
        faults.append(Fault(tool or None, kind, int(times) if times else None))
    return faults


def rename_first_field(result: dict) -> dict:
    first = next(iter(result))
    return {(f"{key}_v2" if key == first else key): v for key, v in result.items()}


class FaultyToolbox:
    def __init__(self, toolbox: Toolbox, spec: str):
        self.toolbox = toolbox
        self.faults = spec  # recorded in the trace of every request
        self.rules = parse(spec)
        unknown = {f.tool for f in self.rules if f.tool} - set(toolbox.tools)
        if unknown:
            raise ValueError(f"no such tools: {', '.join(sorted(unknown))}")
        self.calls: Counter[str] = Counter()

    def schemas(self) -> list[dict]:
        return self.toolbox.schemas()

    def timeout_s(self, name: str) -> float | None:
        return self.toolbox.timeout_s(name)

    def retry_safe(self, name: str) -> bool:
        return self.toolbox.retry_safe(name)

    def side_effect(self, name: str) -> bool:
        return self.toolbox.side_effect(name)

    def start_request(self) -> None:
        """Every request starts with the faults as given: `*N` counts from zero."""
        self.calls.clear()
        self.toolbox.start_request()

    def fault(self, name: str) -> Fault | None:
        """The rule for this call of the tool: the tool's own first, then a general one."""
        rules = [f for f in self.rules if f.tool == name] or [
            f for f in self.rules if f.tool is None
        ]
        for rule in rules:
            if rule.times is None or self.calls[name] <= rule.times:
                return rule
        return None

    def execute(self, call: ToolCall) -> ToolResult:
        self.calls[call.name] += 1
        fault = self.fault(call.name)
        if fault is None:
            return self.toolbox.execute(call)
        if fault.kind == "schema":
            return self.toolbox.execute(call, mutate=rename_first_field)
        if fault.kind == "lost":
            self.toolbox.execute(call)
            return ToolResult(
                f"{call.name}: the connection was lost before the answer arrived.",
                True,
                error_kind="transient",
            )
        if fault.kind == "timeout":
            return ToolResult(
                f"Tool {call.name} timed out.", True, error_kind="timeout"
            )
        if fault.kind == "429":
            return ToolResult(
                f"{call.name}: 429 Too Many Requests, retry after {RETRY_AFTER_S:g} s.",
                True,
                error_kind="transient",
                retry_after=RETRY_AFTER_S,
            )
        return ToolResult(
            f"{call.name}: 503 Service Unavailable.", True, error_kind="transient"
        )
