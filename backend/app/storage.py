"""
Lightweight SQLite persistence so the dashboard has history to display.
No ORM — this is small enough that raw sqlite3 keeps it simple and dependency-free.
"""
import json
import sqlite3
import time
from pathlib import Path
from contextlib import contextmanager

DB_PATH = str(Path(__file__).resolve().parents[1] / "devagent.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                repo_full_name TEXT NOT NULL,
                pr_number INTEGER NOT NULL,
                head_sha TEXT,
                summary TEXT,
                comment_count INTEGER,
                sandbox_exit_code INTEGER,
                error TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS debug_scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                repo_path TEXT NOT NULL,
                mode TEXT NOT NULL,           -- 'scan' or 'analyze'
                root_cause_summary TEXT,
                issue_count INTEGER,
                static_finding_count INTEGER,
                issues_json TEXT,
                static_findings_json TEXT
            )
        """)


def save_review(*, repo_full_name: str, pr_number: int, head_sha: str,
                 summary: str, comment_count: int, sandbox_exit_code: int | None,
                 error: str | None = None) -> int:
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO reviews
               (created_at, repo_full_name, pr_number, head_sha, summary,
                comment_count, sandbox_exit_code, error)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (time.time(), repo_full_name, pr_number, head_sha, summary,
             comment_count, sandbox_exit_code, error),
        )
        return cur.lastrowid


def save_debug_scan(*, repo_path: str, mode: str, result: dict) -> int:
    issues = result.get("issues", [])
    findings = result.get("static_findings", [])
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO debug_scans
               (created_at, repo_path, mode, root_cause_summary,
                issue_count, static_finding_count, issues_json, static_findings_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (time.time(), repo_path, mode, result.get("root_cause_summary", ""),
             len(issues), len(findings), json.dumps(issues), json.dumps(findings)),
        )
        return cur.lastrowid


def list_reviews(limit: int = 50) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def list_debug_scans(limit: int = 50) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM debug_scans ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d["issues"] = json.loads(d.pop("issues_json") or "[]")
            d["static_findings"] = json.loads(d.pop("static_findings_json") or "[]")
            results.append(d)
        return results