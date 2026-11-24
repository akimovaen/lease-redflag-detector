"""Ask the agent one question.

    uv run python -m lease_redflag_detector.agent.cli "Хто погоджує поступки?"
    make agent Q="Хто погоджує поступки?" MAX_STEPS=3
    make agent Q="…" FAULTS=search_corpus:503   (failures on purpose, see faults.py)
    make agent Q="…" AS_USER=litigator               (as another user of configs/users.toml)

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
    parser.add_argument(
        "--as", dest="user", help="user of configs/users.toml (default: the config's)"
    )
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--max-usd", type=float)
    parser.add_argument(
        "--faults",
        default=os.environ.get("FAULTS"),
        help="tool failures to inject, e.g. search_corpus:503 (see agent/faults.py)",
    )
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

    from lease_redflag_detector.agent.faults import FaultyToolbox
    from lease_redflag_detector.agent.loop import Agent, AgentConfig
    from lease_redflag_detector.agent.toolset import build_toolbox
    from lease_redflag_detector.agent.trace import Trace
    from lease_redflag_detector.agent.users import UnknownUser, get_user

    config = AgentConfig.load(args.config)
    try:
        user = get_user(args.user or config.user)
    except UnknownUser as e:
        raise SystemExit(str(e)) from None
    config.user = user.id
    if args.max_steps is not None:
        config.limits.max_steps = args.max_steps
    if args.max_usd is not None:
        config.limits.max_usd = args.max_usd
    print(f"Користувач: {user.describe()}. Loading the search models…", flush=True)
    tools = build_toolbox(config)
    if args.faults:
        tools = FaultyToolbox(tools, args.faults)
        print(f"Injected failures: {args.faults}")
    agent = Agent.from_config(config, tools)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = TRACES / f"{stamp}.jsonl"
    answer = agent.run(args.question, Trace(path))
    called = [
        e["name"]
        + (f"×{e['attempts']}" if e["attempts"] > 1 else "")
        + (f" ({e['error_kind']})" if e["error_kind"] else "")
        for e in answer.trace.tool_calls()
    ]
    print(f"\n{answer.text}\n")
    print(
        f"[{answer.stop_reason} · кроків: {answer.steps} · "
        f"інструменти: {', '.join(called) or 'немає'} · ${answer.cost_usd:.4f} · "
        f"{answer.latency_s:.0f} с · trace: {path.relative_to(ROOT)}]"
    )


if __name__ == "__main__":
    main()
