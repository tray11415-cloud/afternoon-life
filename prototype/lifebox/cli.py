from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .engine import Engine
from .fixtures import neutral_world
from .policies import RemotePolicy
from .runtime import Runtime
from .storage import load, save
from .config import load_router
from .routing import RoutedPolicy, fixture_router


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="AI 生活沙箱底層原型")
    parser.add_argument("command", choices=["demo", "smoke"], nargs="?", default="demo")
    parser.add_argument("--minutes", type=int, default=8)
    parser.add_argument("--save", type=Path)
    parser.add_argument("--load", type=Path)
    parser.add_argument("--remote", action="store_true", help="使用 LIFE_AGENT_ENDPOINT 指向的模型閘道")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--models", type=Path, help="依任務與場合選擇模型的 JSON 設定")
    args = parser.parse_args(argv)
    if args.command == "smoke":
        import unittest
        from .smoke_report import ReportingResult, write_report
        suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / "tests"))
        if suite.countTestCases() == 0:
            parser.error("找不到 smoke test，無法回報通過")
        result = unittest.TextTestRunner(verbosity=2, resultclass=ReportingResult).run(suite)
        if args.report:
            write_report(result, args.report)
        return 0 if result.wasSuccessful() else 1
    if not 1 <= args.minutes <= 1440:
        parser.error("--minutes 必須介於 1 與 1440")
    if args.remote and args.models:
        parser.error("--remote 與 --models 請擇一使用")
    try:
        engine = load(args.load) if args.load else Engine(neutral_world())
        router = None
        if args.remote:
            endpoint = os.environ.get("LIFE_AGENT_ENDPOINT", "")
            if not endpoint:
                parser.error("--remote 需要設定 LIFE_AGENT_ENDPOINT")
            policy = RemotePolicy(endpoint, os.environ.get("LIFE_AGENT_KEY", ""))
        else:
            router = load_router(args.models) if args.models else fixture_router()
            policy = RoutedPolicy(router)
        decisions = Runtime(engine, policy).run(args.minutes)
        state = engine.export_state()
        summary = {"mode": "remote_gateway" if args.remote else "configured_routing" if args.models else "offline_fixture",
                   "tick": engine.tick, "agent_count": len(engine.agent_ids()), "event_count": engine.revision,
                   "completed_goals": sum(actor["goal"]["progress"] >= actor["goal"]["target"]
                                          for actor in state["actors"].values() if actor["role"] == "agent"),
                   "failed_decisions": sum(not item["accepted"] for item in decisions)}
        if router:
            summary["model_usage"] = router.usage()
        if args.save:
            save(engine, args.save)
            summary["save"] = str(args.save)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if summary["failed_decisions"] else 0
    except (OSError, ValueError) as exc:
        print(f"無法完成：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
