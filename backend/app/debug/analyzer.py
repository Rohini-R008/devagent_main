"""
Orchestrates the debugging pipeline:

  analyze_traceback: traceback text -> retrieve relevant code (RAG) ->
                      run static pattern checks -> LLM root-cause + fix
  scan_repo:          no traceback -> run static pattern checks -> for the
                      top findings, retrieve their code context -> LLM
                      summary of the most likely real issues + fixes
"""
import json
import logging

from pydantic import ValidationError

from app.llm_client import get_llm_client
from app.config import settings
from app.debug import indexer, patterns
from app.schemas import DebugResult

logger = logging.getLogger("devagent.debug.analyzer")

DIAGNOSTIC_SYSTEM_PROMPT = """You are an expert PyTorch / CUDA performance engineer.
You diagnose GPU memory fragmentation, OOM errors, and memory leaks in training/inference code.

You are given:
1. An error traceback (if any) or a note that this is a proactive scan.
2. Static-analysis findings from heuristic pattern checks (may include false positives — use judgment).
3. Retrieved code snippets from the repository that are most relevant.

Produce a focused diagnosis. Only report issues you're reasonably confident are real, given the
evidence. For each, give: the likely root cause, the specific file/location, a description of the
fix, and — when the fix is a direct code replacement — the literal replacement code in "patch".
Leave "patch" null if the fix needs broader restructuring than a single replacement.
If nothing concrete stands out, say so plainly instead of inventing issues.

Respond ONLY with JSON, no markdown fences, in this shape:
{
  "root_cause_summary": "1-3 sentence overall diagnosis",
  "issues": [
    {
      "file": "relative/path.py",
      "line": 42,
      "problem": "what's wrong and why it causes memory fragmentation/leaks/OOM",
      "fix": "concrete code-level fix, described precisely",
      "patch": "exact replacement code, or null"
    }
  ]
}
"""


def _format_findings(findings: list[patterns.Finding]) -> str:
    if not findings:
        return "(no static-analysis findings)"
    return "\n".join(
        f"- [{f['rule']}] {f['file']}:{f['line']} — {f['message']}"
        for f in findings
    )


def _format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "(no relevant code retrieved)"
    parts = []
    for c in chunks:
        parts.append(f"--- {c['file']} (starting near line {c['start_line']}) ---\n{c['text']}")
    return "\n\n".join(parts)


def _call_llm(user_content: str) -> dict:
    """Call the LLM and return a validated, plain-dict result. Never raises
    past this point — validation failures are folded into a fallback result
    so callers always get a usable dict."""
    client = get_llm_client()
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": DIAGNOSTIC_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
        )
        raw = resp.choices[0].message.content.strip()
        parsed_json = json.loads(raw)
        result = DebugResult.model_validate(parsed_json)
        return result.model_dump()
    except (json.JSONDecodeError, ValidationError, Exception) as e:  # noqa: BLE001
        logger.exception("LLM diagnosis failed or returned an invalid shape")
        return {"root_cause_summary": f"LLM diagnosis failed: {e}", "issues": []}


def analyze_traceback(repo_path: str, traceback_text: str, collection_name: str | None = None) -> dict:
    collection_name = collection_name or indexer.collection_name_for(repo_path)

    findings = patterns.scan_repo(repo_path)

    try:
        context_chunks = indexer.query_context(collection_name, traceback_text, n_results=6)
    except ValueError:
        # Repo hasn't been indexed yet — index it now, then retry once.
        indexer.index_repo(repo_path, collection_name)
        context_chunks = indexer.query_context(collection_name, traceback_text, n_results=6)

    user_content = (
        f"=== ERROR TRACEBACK ===\n{traceback_text}\n\n"
        f"=== STATIC ANALYSIS FINDINGS ===\n{_format_findings(findings)}\n\n"
        f"=== RETRIEVED CODE CONTEXT ===\n{_format_context(context_chunks)}"
    )

    result = _call_llm(user_content)
    return {**result, "static_findings": findings}


def scan_repo(repo_path: str, collection_name: str | None = None, top_n: int = 8) -> dict:
    collection_name = collection_name or indexer.collection_name_for(repo_path)
    findings = patterns.scan_repo(repo_path)

    if not findings:
        return {
            "root_cause_summary": "No GPU-memory antipatterns detected by static checks.",
            "issues": [],
            "static_findings": [],
        }

    # Index (fresh) so retrieval reflects current code.
    indexer.index_repo(repo_path, collection_name)

    # Use the findings themselves as the retrieval query — pulls in the
    # actual surrounding code for the flagged spots.
    query = "\n".join(f"{f['rule']}: {f['message']}" for f in findings[:top_n])
    context_chunks = indexer.query_context(collection_name, query, n_results=8)

    user_content = (
        "=== ERROR TRACEBACK ===\n(none — this is a proactive scan, no runtime error occurred)\n\n"
        f"=== STATIC ANALYSIS FINDINGS ===\n{_format_findings(findings[:top_n])}\n\n"
        f"=== RETRIEVED CODE CONTEXT ===\n{_format_context(context_chunks)}"
    )

    result = _call_llm(user_content)
    return {**result, "static_findings": findings}
