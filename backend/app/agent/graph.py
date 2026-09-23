"""
Wires the review nodes into a LangGraph StateGraph:

    fetch_diff -> fetch_repo_snapshot -> retrieve_context -> run_sandbox
                -> analyze -> post_review -> END

Exposes `run_review_agent`, called by the webhook handler as a background task.
"""
import logging

from langgraph.graph import StateGraph, END

from app.agent.nodes import (
    ReviewState,
    fetch_diff,
    fetch_repo_snapshot,
    retrieve_context,
    run_sandbox,
    analyze,
    post_review,
)

logger = logging.getLogger("devagent.graph")


def build_graph():
    graph = StateGraph(ReviewState)

    graph.add_node("fetch_diff", fetch_diff)
    graph.add_node("fetch_repo_snapshot", fetch_repo_snapshot)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("run_sandbox", run_sandbox)
    graph.add_node("analyze", analyze)
    graph.add_node("post_review", post_review)

    graph.set_entry_point("fetch_diff")
    graph.add_edge("fetch_diff", "fetch_repo_snapshot")
    graph.add_edge("fetch_repo_snapshot", "retrieve_context")
    graph.add_edge("retrieve_context", "run_sandbox")
    graph.add_edge("run_sandbox", "analyze")
    graph.add_edge("analyze", "post_review")
    graph.add_edge("post_review", END)

    return graph.compile()


# Compile once at import time; reused across requests.
_compiled_graph = build_graph()


async def run_review_agent(repo_full_name: str, pr_number: int, head_sha: str) -> ReviewState:
    initial_state: ReviewState = {
        "repo_full_name": repo_full_name,
        "pr_number": pr_number,
        "head_sha": head_sha,
    }

    logger.info("Starting review agent for %s#%s", repo_full_name, pr_number)
    final_state = await _compiled_graph.ainvoke(initial_state)

    if final_state.get("error"):
        logger.error("Review agent finished with error: %s", final_state["error"])
    else:
        logger.info("Review agent finished for %s#%s", repo_full_name, pr_number)

    return final_state
