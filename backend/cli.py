#!/usr/bin/env python3
"""
Standalone CLI for DevAgent's PyTorch/CUDA debugging module.

Usage:
  python cli.py index <repo_path>
  python cli.py analyze <repo_path> --traceback-file path/to/error.txt
  python cli.py analyze <repo_path> --traceback-text "RuntimeError: CUDA out of memory..."
  python cli.py scan <repo_path>
"""
import argparse
import json
import sys

from app.debug import indexer, analyzer
from app import storage


def cmd_index(args):
    result = indexer.index_repo(args.repo_path)
    print(json.dumps(result, indent=2))


def cmd_analyze(args):
    if args.traceback_file:
        traceback_text = open(args.traceback_file, encoding="utf-8").read()
    elif args.traceback_text:
        traceback_text = args.traceback_text
    else:
        print("Provide --traceback-file or --traceback-text", file=sys.stderr)
        sys.exit(1)

    storage.init_db()
    result = analyzer.analyze_traceback(args.repo_path, traceback_text)
    storage.save_debug_scan(repo_path=args.repo_path, mode="analyze", result=result)
    _print_result(result)


def cmd_scan(args):
    storage.init_db()
    result = analyzer.scan_repo(args.repo_path)
    storage.save_debug_scan(repo_path=args.repo_path, mode="scan", result=result)
    _print_result(result)

def _print_result(result: dict):
    print("\n=== ROOT CAUSE SUMMARY ===")
    print(result.get("root_cause_summary", "(none)"))

    issues = result.get("issues", [])
    if issues:
        print(f"\n=== ISSUES ({len(issues)}) ===")
        for i, issue in enumerate(issues, 1):
            print(f"\n{i}. {issue.get('file')}:{issue.get('line')}")
            print(f"   Problem: {issue.get('problem')}")
            print(f"   Fix:     {issue.get('fix')}")

    findings = result.get("static_findings", [])
    if findings:
        print(f"\n=== RAW STATIC-ANALYSIS FINDINGS ({len(findings)}) ===")
        for f in findings:
            print(f"  [{f['rule']}] {f['file']}:{f['line']} — {f['message']}")


def main():
    parser = argparse.ArgumentParser(description="DevAgent PyTorch/CUDA debugger")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Index a repo's Python files into ChromaDB")
    p_index.add_argument("repo_path")
    p_index.set_defaults(func=cmd_index)

    p_analyze = sub.add_parser("analyze", help="Diagnose a specific error traceback")
    p_analyze.add_argument("repo_path")
    p_analyze.add_argument("--traceback-file")
    p_analyze.add_argument("--traceback-text")
    p_analyze.set_defaults(func=cmd_analyze)

    p_scan = sub.add_parser("scan", help="Proactively scan for memory-issue patterns")
    p_scan.add_argument("repo_path")
    p_scan.set_defaults(func=cmd_scan)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()