"""
Receives GitHub webhook events, verifies the signature, and kicks off
the review agent (in the background) for relevant pull_request events.
"""
import hashlib
import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from pydantic import ValidationError

from app.config import settings
from app.agent.graph import run_review_agent
from app.schemas import PullRequestWebhookPayload

logger = logging.getLogger("devagent.webhook")

router = APIRouter()

# PR actions worth reviewing
RELEVANT_ACTIONS = {"opened", "synchronize", "reopened"}


def verify_signature(payload_body: bytes, signature_header: str | None) -> None:
    """Raise HTTPException if the X-Hub-Signature-256 header doesn't match."""
    if not settings.github_webhook_secret:
        # No secret configured (e.g. local dev) -> skip verification.
        return

    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    expected = "sha256=" + hmac.new(
        key=settings.github_webhook_secret.encode(),
        msg=payload_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    raw_body = await request.body()
    verify_signature(raw_body, x_hub_signature_256)

    raw_payload = await request.json()

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event={x_github_event}"}

    # Validate shape before touching any fields — a malformed or unexpected
    # payload now returns a clean 400 instead of an unhandled KeyError.
    try:
        payload = PullRequestWebhookPayload.model_validate(raw_payload)
    except ValidationError as e:
        logger.warning("Rejected malformed webhook payload: %s", e)
        raise HTTPException(status_code=400, detail="Malformed pull_request payload")

    if payload.action not in RELEVANT_ACTIONS:
        return {"status": "ignored", "reason": f"action={payload.action}"}

    repo_full_name = payload.repository.full_name
    pr_number = payload.pull_request.number
    head_sha = payload.pull_request.head.sha

    logger.info("Queuing review for %s#%s (%s)", repo_full_name, pr_number, head_sha)

    background_tasks.add_task(run_review_agent, repo_full_name, pr_number, head_sha)

    return {"status": "queued", "repo": repo_full_name, "pr_number": pr_number}
