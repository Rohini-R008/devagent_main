"""
Individual LangGraph nodes for the PR review agent:
  1. fetch_diff          - pull the PR's changed files/diff from GitHub
  2. fetch_repo_snapshot  - download the full repo at head_sha
  3. retrieve_context      - RAG: index the snapshot, retrieve chunks relevant to the diff
  4. run_sandbox            - lint + test the snapshot in an isolated Docker container
  5. analyze                 - ask the LLM to review, grounded in diff + context + sandbox output
  6. post_review               - publish the review (with applicable suggestions) to GitHub
"""
import asyncio
import json
import logging
import os
import shutil
import tarfile
import tempfile
import uuid
from typing import Any, TypedDict

import httpx
from pydantic import ValidationError

from app.config import settings
from app.llm_client import get_llm_client
from app.sandbox import runner as sandbox_runner
from app.sandbox.error_parser import parse_runtime_errors
from app.debug import indexer
from app.schemas import ReviewResult
from app import storage

logger = logging.getLogger("devagent.nodes")

GITHUB_API = "https://api.github.com"


class ReviewState(TypedDict, total=False):
    repo_full_name: str
    pr_number: int
    head_sha: str
    diff_text: str
    files: list[dict]
    summary: str
    comments: list[dict]   # [{path, line, body, suggestion}]
    local_repo_dir: str
    _tmp_dir: str
    retrieved_context: list[dict]
    sandbox_logs: str
    sandbox_exit_code: int
    sandbox_timed_out: bool
    sandbox_duration_seconds: float
    runtime_errors: list[dict]
    error: str


def _github_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def fetch_diff(state: ReviewState) -> ReviewState:
    """Fetch the list of changed files + patches for the PR."""
    repo = state["repo_full_name"]
    pr_number = state["pr_number"]
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/files"

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=_github_headers(), params={"per_page": 100})
            resp.raise_for_status()
            files = resp.json()
    except httpx.HTTPError as e:
        logger.exception("Failed to fetch PR files")
        return {**state, "error": f"fetch_diff failed: {e}"}

    # Build a compact diff string the LLM can reason about.
    diff_chunks = []
    for f in files:
        patch = f.get("patch", "")  # binary files have no patch
        if patch:
            diff_chunks.append(f"--- {f['filename']} ---\n{patch}")

    return {
        **state,
        "files": files,
        "diff_text": "\n\n".join(diff_chunks)[:12000],  # keep prompt bounded
    }


async def fetch_repo_snapshot(state: ReviewState) -> ReviewState:
    """Download a tarball snapshot of the repo at head_sha into a temp dir."""
    if state.get("error"):
        return state

    repo = state["repo_full_name"]
    sha = state["head_sha"]
    url = f"{GITHUB_API}/repos/{repo}/tarball/{sha}"

    tmp_dir = tempfile.mkdtemp(prefix="devagent_")
    tarball_path = os.path.join(tmp_dir, "repo.tar.gz")

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(url, headers=_github_headers())
            resp.raise_for_status()
        with open(tarball_path, "wb") as f:
            f.write(resp.content)
        with tarfile.open(tarball_path) as tar:
            tar.extractall(tmp_dir)
    except (httpx.HTTPError, tarfile.TarError, OSError) as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.exception("Failed to fetch repo snapshot")
        return {**state, "error": f"fetch_repo_snapshot failed: {e}"}

    # GitHub tarballs extract into a single subdir like "owner-repo-<sha7>"
    subdirs = [
        d for d in os.listdir(tmp_dir)
        if os.path.isdir(os.path.join(tmp_dir, d))
    ]
    repo_dir = os.path.join(tmp_dir, subdirs[0]) if subdirs else tmp_dir

    return {**state, "local_repo_dir": repo_dir, "_tmp_dir": tmp_dir}


async def retrieve_context(state: ReviewState) -> ReviewState:
    """
    RAG step: index the repo snapshot into a throwaway ChromaDB collection
    and retrieve chunks relevant to the diff, so the reviewer sees related
    code across the repo — not just the changed lines in isolation.
    The collection is deleted immediately after use; it only needs to live
    for the duration of this one retrieval.
    """
    if state.get("error"):
        return state

    local_dir = state.get("local_repo_dir")
    if not local_dir or not state.get("diff_text"):
        return {**state, "retrieved_context": []}

    collection_name = f"pr_{uuid.uuid4().hex[:16]}"
    chunks: list[dict] = []
    try:
        await asyncio.to_thread(indexer.index_repo, local_dir, collection_name)
        chunks = await asyncio.to_thread(
            indexer.query_context, collection_name, state["diff_text"], 6
        )
    except Exception as e:  # noqa: BLE001 - RAG is an enhancement, never fatal to the review
        logger.warning("RAG context retrieval failed, continuing without it: %s", e)
    finally:
        try:
            indexer.get_chroma_client().delete_collection(collection_name)
        except Exception:
            pass

    return {**state, "retrieved_context": chunks}


async def run_sandbox(state: ReviewState) -> ReviewState:
    """Run lint + tests on the snapshot inside isolated Docker containers."""
    if state.get("error"):
        return state

    local_dir = state.get("local_repo_dir")
    tmp_dir = state.get("_tmp_dir")

    if not local_dir:
        return {**state, "error": "run_sandbox: no local repo directory available"}

    try:
        result = await asyncio.to_thread(sandbox_runner.run_checks, local_dir)
    except RuntimeError as e:
        # e.g. Docker daemon not reachable — don't kill the whole review,
        # just proceed without sandbox results.
        logger.warning("Sandbox unavailable, skipping: %s", e)
        return {**state, "sandbox_logs": f"(sandbox skipped: {e})"}
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    runtime_errors = parse_runtime_errors(result["logs"])

    return {
        **state,
        "sandbox_logs": result["logs"],
        "sandbox_exit_code": result["exit_code"],
        "sandbox_timed_out": result["timed_out"],
        "sandbox_duration_seconds": result["duration_seconds"],
        "runtime_errors": runtime_errors,
    }


REVIEW_SYSTEM_PROMPT = """You are an expert senior software engineer performing a pull request code review.
You are given: a unified diff, related code retrieved from elsewhere in the repo (via vector search),
structured runtime test failures (if any occurred), and the raw sandbox output.

Ground your review in this evidence — e.g. if tests failed, name the specific failing test and why;
if lint errors appeared, point to them specifically. Use the retrieved context to catch issues that
span multiple files (e.g. a changed function signature that breaks a caller elsewhere in the repo).
Also identify concrete issues from the diff itself: bugs, security problems, missing error handling,
style inconsistencies, and missed edge cases. Do not comment on things that are fine. If everything
looks solid, say so briefly.

For each comment, if you can state the exact fix as a code replacement, include it in "suggestion" —
this must be the literal replacement code for that line (or block), nothing else. Leave it null if
the fix isn't a simple direct replacement (e.g. requires broader restructuring).

Respond ONLY with JSON in this exact shape, no markdown fences:
{
  "summary": "1-3 sentence overall assessment",
  "comments": [
    {"path": "relative/file/path.py", "line": 42, "body": "specific, actionable comment", "suggestion": "exact replacement code, or null"}
  ]
}
"""


def _format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "(no related code retrieved)"
    return "\n\n".join(
        f"--- {c['file']} (near line {c['start_line']}) ---\n{c['text']}"
        for c in chunks
    )


def _format_runtime_errors(errors: list[dict]) -> str:
    if not errors:
        return "(no runtime test failures detected)"
    return "\n".join(
        f"- [{e['kind']}] {e['file']}::{e['test_name']} — {e['error_type']}: {e['message']}"
        for e in errors
    )


async def analyze(state: ReviewState) -> ReviewState:
    """Send the diff + context + sandbox findings to the LLM; validate its output."""
    if state.get("error"):
        return state
    if not state.get("diff_text"):
        return {**state, "summary": "No reviewable text diff found.", "comments": []}

    client = get_llm_client()

    user_content = (
        f"=== DIFF ===\n{state['diff_text']}\n\n"
        f"=== RELATED CODE (retrieved via RAG) ===\n{_format_context(state.get('retrieved_context', []))}\n\n"
        f"=== RUNTIME TEST FAILURES (parsed) ===\n{_format_runtime_errors(state.get('runtime_errors', []))}\n\n"
        f"=== RAW SANDBOX OUTPUT (lint + tests) ===\n{state.get('sandbox_logs', '(sandbox did not run)')}"
    )

    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
        )
        raw = resp.choices[0].message.content.strip()
        parsed_json = json.loads(raw)
        result = ReviewResult.model_validate(parsed_json)
    except (json.JSONDecodeError, ValidationError, Exception) as e:  # noqa: BLE001
        logger.exception("LLM analysis failed or returned an invalid shape")
        return {**state, "error": f"analyze failed: {e}"}

    return {
        **state,
        "summary": result.summary,
        "comments": [c.model_dump() for c in result.comments],
    }


async def post_review(state: ReviewState) -> ReviewState:
    """Post the summary + inline comments (with applicable suggestions) to GitHub."""
    if state.get("error"):
        logger.warning("Skipping post_review due to earlier error: %s", state["error"])
        storage.save_review(
            repo_full_name=state.get("repo_full_name", ""),
            pr_number=state.get("pr_number", 0),
            head_sha=state.get("head_sha", ""),
            summary="",
            comment_count=0,
            sandbox_exit_code=state.get("sandbox_exit_code"),
            error=state["error"],
        )
        return state

    repo = state["repo_full_name"]
    pr_number = state["pr_number"]
    url = f"{GITHUB_API}/repos/{repo}/pulls/{pr_number}/reviews"

    review_comments = []
    for c in state.get("comments", []):
        if not (c.get("path") and c.get("line") and c.get("body")):
            continue
        body = c["body"]
        # GitHub natively renders ```suggestion blocks as one-click-applicable
        # code changes on a PR review comment.
        if c.get("suggestion"):
            body = f"{body}\n\n```suggestion\n{c['suggestion']}\n```"
        review_comments.append({"path": c["path"], "line": c["line"], "body": body})

    body: dict[str, Any] = {
        "commit_id": state["head_sha"],
        "body": state.get("summary", "Automated review by DevAgent."),
        "event": "COMMENT",  # use "REQUEST_CHANGES" / "APPROVE" if you want the agent to gate merges
        "comments": review_comments,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=_github_headers(), json=body)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.exception("Failed to post review")
        storage.save_review(
            repo_full_name=repo, pr_number=pr_number, head_sha=state.get("head_sha", ""),
            summary=state.get("summary", ""), comment_count=len(review_comments),
            sandbox_exit_code=state.get("sandbox_exit_code"),
            error=f"post_review failed: {e}",
        )
        return {**state, "error": f"post_review failed: {e}"}

    storage.save_review(
        repo_full_name=repo, pr_number=pr_number, head_sha=state.get("head_sha", ""),
        summary=state.get("summary", ""), comment_count=len(review_comments),
        sandbox_exit_code=state.get("sandbox_exit_code"), error=None,
    )

    return state
