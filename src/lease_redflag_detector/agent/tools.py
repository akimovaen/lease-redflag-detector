"""Tools of the agent: a description, schemas of the arguments and the result, a function.

The description the model reads lives in `prompts/tools/<name>_v<N>.md`, versioned like
the prompts; the argument schema goes to the model with it. A tool of an MCP server
comes with the description and schema the server gives (`spec`). Before a call the arguments
are validated against that schema, and after it the result against its own: a tool
whose result changed shape fails loudly instead of handing the model a silent None.

Every tool says whether it changes anything outside the conversation (`side_effect`)
and whether a failed call may be repeated (`retry_safe`); the loop and the fault
handling read these flags, not the descriptions.

A tool reports an expected failure (an unknown lease, a quote not in the lease) by
raising `ToolError`, whose message goes to the model (`AccessDenied` when the lawyer
may not see it), and a failure that may pass on a repeat (429, 503, a timeout of the
service behind it) by raising `TransientError`; the loop decides whether to repeat. A tool that calls a model itself returns `Priced`
so that the cost counts toward the budget of the request, even when the call failed.

Every failed call gets an `error_kind`, which the loop and the trace use.
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


class TransientError(ToolError):
    """A failure that may pass if the call is repeated: 429, 503, a timeout."""

    def __init__(
        self, message: str, cost_usd: float = 0.0, retry_after: float | None = None
    ):
        super().__init__(message, cost_usd)
        self.retry_after = retry_after


class AccessDenied(ToolError):
    """The lawyer may not see this: no retry and no other tool can get past it."""


# Errors of the Anthropic SDK that a repeat may get past; the other ones (a bad
# request, authentication) would fail the same way again.
TRANSIENT_API_ERRORS = (
    "RateLimitError",
    "OverloadedError",
    "InternalServerError",
    "ServiceUnavailableError",
    "DeadlineExceededError",
    "APITimeoutError",
    "APIConnectionError",
)


def api_failure(what: str, error: str | None, cost_usd: float) -> ToolError:
    """The error of a stage 1 or 2 call, which reports an API error as the text
    "<ExceptionName>: <message>"."""
    transient = (error or "").startswith(TRANSIENT_API_ERRORS)
    return (TransientError if transient else ToolError)(f"{what}: {error}", cost_usd)


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
    # A tool of an MCP server: the name, description and schema the server gives,
    # sent to the model as they are. The arguments are still validated by `args`.
    spec: dict | None = None

    def schema(self) -> dict:
        if self.spec:
            return self.spec
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
    def __init__(
        self,
        tools: list[Tool],
        on_request: list[Callable[[], None]] | None = None,
        state: Callable[[], str] | None = None,
    ):
        """`on_request`: what to reset at the start of every request, such as the
        redlines a request has drafted. `state`: what the tools hold from earlier
        questions of a conversation, told to the model (`chat.Session`)."""
        self.tools = {tool.name: tool for tool in tools}
        self._schemas = [tool.schema() for tool in tools]
        self.on_request = on_request or []
        self._state = state

    def state(self) -> str:
        return self._state() if self._state else ""

    def start_request(self) -> None:
        for reset in self.on_request:
            reset()

    def schemas(self) -> list[dict]:
        return self._schemas

    def timeout_s(self, name: str) -> float | None:
        tool = self.tools.get(name)
        return tool.timeout_s if tool else None

    def retry_safe(self, name: str) -> bool:
        tool = self.tools.get(name)
        return bool(tool and tool.retry_safe and not tool.side_effect)

    def side_effect(self, name: str) -> bool:
        tool = self.tools.get(name)
        return bool(tool and tool.side_effect)

    def execute(
        self, call: ToolCall, mutate: Callable[[dict], dict] | None = None
    ) -> ToolResult:
        """`mutate` changes the raw result before it is validated (faults.py)."""
        tool = self.tools.get(call.name)
        if tool is None:
            return ToolResult(
                f"Unknown tool {call.name!r}; available: {', '.join(self.tools)}.",
                True,
                error_kind="unknown_tool",
            )
        try:
            args = tool.args.model_validate(call.args)
        except ValidationError as e:
            return ToolResult(
                f"Invalid arguments for {call.name}: {errors_text(e)}",
                True,
                error_kind="invalid_args",
            )
        cost = 0.0
        try:
            output = tool.fn(args)
        except TransientError as e:
            return ToolResult(
                str(e),
                True,
                e.cost_usd,
                error_kind="transient",
                retry_after=e.retry_after,
            )
        except AccessDenied as e:
            return ToolResult(str(e), True, e.cost_usd, error_kind="denied")
        except ToolError as e:
            return ToolResult(str(e), True, e.cost_usd, error_kind="tool_error")
        if isinstance(output, Priced):
            output, cost = output.output, output.cost_usd
        raw = (
            output.model_dump(mode="json") if isinstance(output, BaseModel) else output
        )
        if mutate:
            raw = mutate(raw)
        try:
            result = tool.result.model_validate(raw)
        except ValidationError as e:
            return ToolResult(
                f"{call.name} returned a result in an unexpected format: "
                f"{errors_text(e)}. Its output format has changed.",
                True,
                cost,
                error_kind="schema",
            )
        return ToolResult(result.model_dump_json(), cost_usd=cost)
