"""Ask the agent one question.

    uv run python -m lease_redflag_detector.agent.cli "Хто погоджує поступки?"
    make agent Q="Хто погоджує поступки?" MAX_STEPS=3

Prints the answer and a line with the stop reason, steps, cost and the trace, which
goes to results/agent/traces/ (not committed).
"""

import argparse
import datetime
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "configs" / "agent-haiku-v1.toml"
TRACES = ROOT / "results" / "agent" / "traces"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--max-usd", type=float)
    args = parser.parse_args()
    if not args.question.strip():
        raise SystemExit('No question: make agent Q="…"')
    os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    load_dotenv(ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set: add it to .env (see .env.example)"
        )

    from lease_redflag_detector.agent.loop import Agent, AgentConfig
    from lease_redflag_detector.agent.toolset import build_toolbox
    from lease_redflag_detector.agent.trace import Trace

    config = AgentConfig.load(args.config)
    if args.max_steps:
        config.limits.max_steps = args.max_steps
    if args.max_usd:
        config.limits.max_usd = args.max_usd
    print("Loading the search models…", flush=True)
    agent = Agent.from_config(config, build_toolbox(config))
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = TRACES / f"{stamp}.jsonl"
    answer = agent.run(args.question, Trace(path))
    tools = [e["name"] for e in answer.trace.tool_calls()]
    print(f"\n{answer.text}\n")
    print(
        f"[{answer.stop_reason} · кроків: {answer.steps} · "
        f"інструменти: {', '.join(tools) or 'немає'} · ${answer.cost_usd:.4f} · "
        f"{answer.latency_s:.0f} с · trace: {path.relative_to(ROOT)}]"
    )


if __name__ == "__main__":
    main()
