"""Tools of the agent: a description, schemas of the arguments and the result, a function.

The description the model reads lives in `prompts/tools/<name>_v<N>.md`, versioned like
the prompts; the argument schema goes to the model with it. Before a call the arguments
are validated against that schema, and after it the result against its own: a tool
whose result changed shape fails loudly instead of handing the model a silent None.

Every tool says whether it changes anything outside the conversation (`side_effect`)
and whether a failed call may be repeated (`retry_safe`); the loop and the fault
handling read these flags, not the descriptions.

A tool reports an expected failure (an unknown lease, a quote not in the lease) by
raising `ToolError`, whose message goes to the model. A tool that calls a model itself
returns `Priced` so that the cost counts toward the budget of the request, even when
the call failed.
"""

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from lease_redflag_detector.agent.loop import ToolCall, ToolResult
from lease_redflag_detector.extraction.extractor import load_prompt


class ToolError(Exception):
    """A failure the model should read and may work around."""

    def __init__(self, message: str, cost_usd: float = 0.0):
        super().__init__(message)
        self.cost_usd = cost_usd


@dataclass
class Priced:
    output: BaseModel | dict
    cost_usd: float


@dataclass
class Tool:
    name: str
    description: str  # prompt name, e.g. tools/search_corpus_v1
    args: type[BaseModel]
    result: type[BaseModel]
    fn: Callable[[BaseModel], BaseModel | dict | Priced]
    side_effect: bool = False
    retry_safe: bool = True
    timeout_s: float | None = None  # None: the default of the agent's limits

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": load_prompt(self.description),
            "input_schema": self.args.model_json_schema(),
        }


def errors_text(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, e['loc'])) or '(arguments)'}: {e['msg']}"
        for e in error.errors()
    )


class Toolbox:
    def __init__(self, tools: list[Tool]):
        self.tools = {tool.name: tool for tool in tools}
        self._schemas = [tool.schema() for tool in tools]

    def schemas(self) -> list[dict]:
        return self._schemas

    def timeout_s(self, name: str) -> float | None:
        tool = self.tools.get(name)
        return tool.timeout_s if tool else None

    def execute(self, call: ToolCall) -> ToolResult:
        tool = self.tools.get(call.name)
        if tool is None:
            return ToolResult(
                f"Unknown tool {call.name!r}; available: {', '.join(self.tools)}.", True
            )
        try:
            args = tool.args.model_validate(call.args)
        except ValidationError as e:
            return ToolResult(
                f"Invalid arguments for {call.name}: {errors_text(e)}", True
            )
        cost = 0.0
        try:
            output = tool.fn(args)
        except ToolError as e:
            return ToolResult(str(e), True, e.cost_usd)
        if isinstance(output, Priced):
            output, cost = output.output, output.cost_usd
        try:
            result = tool.result.model_validate(
                output.model_dump() if isinstance(output, BaseModel) else output
            )
        except ValidationError as e:
            return ToolResult(
                f"{call.name} returned a result in an unexpected format: "
                f"{errors_text(e)}",
                True,
                cost,
            )
        return ToolResult(result.model_dump_json(), cost_usd=cost)
