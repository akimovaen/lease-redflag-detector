"""The trace of one agent request: every model call and tool call, as JSON lines.

Each event is written as soon as it happens, so a request that crashes or is killed
still leaves the steps it made. The evals read the trace to check which tools the
agent called, whether it acted without permission, its steps, cost and stop reason.
"""

import json
import time
from pathlib import Path

from lease_redflag_detector.extraction.metrics import cost_usd


class Trace:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.events: list[dict] = []
        self.cost_usd = 0.0
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")

    def add(self, kind: str, **fields) -> dict:
        event = {"kind": kind, "time": round(time.time(), 3), **fields}
        self.events.append(event)
        if self.path:
            with self.path.open("a") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event

    def model_call(
        self, step: int, model: str, reply, latency_s: float, final_only: bool
    ):
        # A model without a price (a fake, a local model) costs nothing.
        cost = cost_usd(model, reply.input_tokens, reply.output_tokens) or 0.0
        self.cost_usd += cost
        return self.add(
            "model",
            step=step,
            final_only=final_only,
            text=reply.text,
            tool_calls=[{"name": c.name, "args": c.args} for c in reply.tool_calls],
            stop_reason=reply.stop_reason,
            input_tokens=reply.input_tokens,
            output_tokens=reply.output_tokens,
            cost_usd=round(cost, 6),
            latency_s=round(latency_s, 3),
        )

    def tool_call(self, step: int, call, result, latency_s: float):
        self.cost_usd += result.cost_usd
        return self.add(
            "tool",
            step=step,
            name=call.name,
            args=call.args,
            content=result.content,
            is_error=result.is_error,
            error_kind=result.error_kind,
            attempts=result.attempts,
            cost_usd=round(result.cost_usd, 6),
            latency_s=round(latency_s, 3),
        )

    def tool_calls(self) -> list[dict]:
        return [e for e in self.events if e["kind"] == "tool"]
