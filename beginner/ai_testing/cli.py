"""Command line entry point for evidence-first AI-assisted testing."""
from __future__ import annotations
import argparse
from pathlib import Path
from .assistant import ask, failure_report, suggest_cases

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = PROJECT_ROOT / "beginner/artifacts/ai"

def build_parser() -> argparse.ArgumentParser:
    app = argparse.ArgumentParser(description="jshERP AI 辅助测试工具（证据优先、人工审核）")
    sub = app.add_subparsers(dest="command", required=True)
    for name in ("ask", "suggest"):
        command = sub.add_parser(name); command.add_argument("question")
        command.add_argument("--local-only", action="store_true"); command.add_argument("--output", type=Path)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--junit", type=Path, required=True); analyze.add_argument("--local-only", action="store_true"); analyze.add_argument("--output", type=Path)
    return app

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "ask":
        result, default = ask(PROJECT_ROOT, args.question, not args.local_only), OUTPUT / "knowledge-answer.md"
    elif args.command == "suggest":
        result, default = suggest_cases(PROJECT_ROOT, args.question, not args.local_only), OUTPUT / "candidate-test-points.md"
    else:
        junit = args.junit if args.junit.is_absolute() else PROJECT_ROOT / args.junit
        result, default = failure_report(PROJECT_ROOT, junit, not args.local_only), OUTPUT / "failure-analysis.md"
    output = args.output or default
    if not output.is_absolute(): output = PROJECT_ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result + "\n", encoding="utf-8")
    print(output)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
