#!/usr/bin/env python3
"""
Benchmarks DevAgent's review turnaround against manual review time, to
produce a real, defensible number instead of an estimate.

Usage:
  # Step 1: for each PR you want to benchmark, manually review it while
  # timing yourself with this stopwatch (press Enter to start, Enter again
  # to stop when you'd have finished writing your review comments):
  python benchmark.py record roshangowda275/devagent-test 4

  # Step 2: once you've recorded manual times for a few PRs, generate the report:
  python benchmark.py report roshangowda275/devagent-test
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import settings
from app import storage

BENCHMARK_FILE = Path(__file__).resolve().parent / "benchmark_data.json"
GITHUB_API = "https://api.github.com"


def _load_data() -> dict:
    if BENCHMARK_FILE.exists():
        return json.loads(BENCHMARK_FILE.read_text())
    return {}


def _save_data(data: dict) -> None:
    BENCHMARK_FILE.write_text(json.dumps(data, indent=2))


def cmd_record(args):
    key = f"{args.repo}#{args.pr_number}"
    input(f"Recording manual review time for {key}. Press Enter to START the timer...")
    start = time.monotonic()
    input("Timer running. Review the PR now — press Enter to STOP when you'd post your comments...")
    elapsed = time.monotonic() - start

    data = _load_data()
    data[key] = {"repo": args.repo, "pr_number": args.pr_number, "manual_seconds": round(elapsed, 1)}
    _save_data(data)

    print(f"Recorded: {elapsed:.1f}s manual review time for {key}")


def _github_headers():
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
    }


def _fetch_pr_created_at(repo: str, pr_number: int) -> float:
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}"
    resp = httpx.get(url, headers=_github_headers(), timeout=30)
    resp.raise_for_status()
    created_at_str = resp.json()["created_at"]  # e.g. "2026-08-01T12:00:00Z"
    dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
    return dt.timestamp()


def cmd_report(args):
    data = _load_data()
    entries = [v for v in data.values() if v["repo"] == args.repo]

    if not entries:
        print(f"No recorded manual times for {args.repo}. Run 'record' first.", file=sys.stderr)
        sys.exit(1)

    all_reviews = {r["pr_number"]: r for r in storage.list_reviews(limit=200)
                   if r["repo_full_name"] == args.repo}

    rows = []
    for entry in entries:
        pr_number = entry["pr_number"]
        review = all_reviews.get(pr_number)
        if not review:
            print(f"  (skipping PR #{pr_number} — no DevAgent review found in devagent.db)")
            continue

        pr_created_at = _fetch_pr_created_at(args.repo, pr_number)
        devagent_seconds = review["created_at"] - pr_created_at
        manual_seconds = entry["manual_seconds"]

        if devagent_seconds <= 0:
            print(f"  (skipping PR #{pr_number} — timestamp anomaly, devagent_seconds={devagent_seconds:.1f})")
            continue

        pct_saved = (manual_seconds - devagent_seconds) / manual_seconds * 100
        rows.append((pr_number, manual_seconds, devagent_seconds, pct_saved))

    if not rows:
        print("No comparable rows to report.", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'PR':<6}{'Manual (s)':<14}{'DevAgent (s)':<16}{'% time saved':<14}")
    print("-" * 50)
    for pr_number, manual_s, devagent_s, pct in rows:
        print(f"#{pr_number:<5}{manual_s:<14.1f}{devagent_s:<16.1f}{pct:<14.1f}")

    avg_pct = sum(r[3] for r in rows) / len(rows)
    print("-" * 50)
    print(f"Average time saved across {len(rows)} PR(s): {avg_pct:.1f}%\n")


def main():
    parser = argparse.ArgumentParser(description="Benchmark DevAgent vs manual review time")
    sub = parser.add_subparsers(dest="command", required=True)

    p_record = sub.add_parser("record", help="Time yourself manually reviewing a PR")
    p_record.add_argument("repo", help="e.g. yourname/devagent-test")
    p_record.add_argument("pr_number", type=int)
    p_record.set_defaults(func=cmd_record)

    p_report = sub.add_parser("report", help="Generate the comparison report")
    p_report.add_argument("repo", help="e.g. yourname/devagent-test")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
