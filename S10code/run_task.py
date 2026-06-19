"""Session 10: direct single-task runner for the computer_use skill.

Builds a one-node spec and invokes ComputerUseSkill.run() directly — clean
for demoing/recording one task without the Planner. The orchestrator path
(flow.py emitting computer_use nodes) remains the catalog-integration proof.

Usage:
  uv run python run_task.py calculator --expr "12.5*8+100="
  uv run python run_task.py electron --content "hello from the agent"
  uv run python run_task.py canvas
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from schemas import NodeSpec


def build_node(task: str, *, expr: str | None = None,
               content: str | None = None, goal: str | None = None) -> NodeSpec:
    meta: dict = {"task": task}
    if expr is not None:
        meta["expression"] = expr
    if content is not None:
        meta["content"] = content
    if goal is not None:
        meta["goal"] = goal
    return NodeSpec(skill="computer_use", inputs=[], metadata=meta)


async def _run(node: NodeSpec) -> int:
    from computer_use.skill import ComputerUseSkill
    root = Path(__file__).parent / "state" / "sessions" / "direct" / "computer_use"
    sk = ComputerUseSkill(
        artifacts_root=str(root), session="direct",
        slowmo_ms=int(os.environ.get("CU_SLOWMO_MS", "0") or "0"),
    )
    result = await sk.run(node)
    print(f"success={result.success} path={result.output.get('path')} "
          f"result={result.output.get('result')!r} "
          f"vision_calls={result.output.get('vision_calls')}")
    print(f"trajectory: {result.output.get('trajectory_dir')}")
    if result.error:
        print(f"error[{result.error_code}]: {result.error}")
    return 0 if result.success else 1


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("task", choices=["calculator", "electron", "canvas"])
    p.add_argument("--expr", default="12.5*8+100=")
    p.add_argument("--content", default="Hello from the computer-use agent.")
    p.add_argument("--goal", default=None)
    args = p.parse_args(argv)
    node = build_node(args.task, expr=args.expr, content=args.content,
                      goal=args.goal)
    return asyncio.run(_run(node))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
