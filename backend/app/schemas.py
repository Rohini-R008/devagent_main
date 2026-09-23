"""
Pydantic schemas for:
  - Validating incoming GitHub webhook payloads (instead of raw dict access)
  - Validating LLM JSON output before it's trusted downstream

Keeping these in one place makes it obvious what shape of data flows
through the system at each boundary.
"""
from pydantic import BaseModel, Field


# --- GitHub webhook payload (only the fields we actually use) --------------

class PullRequestHead(BaseModel):
    sha: str


class PullRequest(BaseModel):
    number: int
    head: PullRequestHead


class Repository(BaseModel):
    full_name: str


class PullRequestWebhookPayload(BaseModel):
    action: str
    pull_request: PullRequest
    repository: Repository


# --- LLM output: PR review -------------------------------------------------

class ReviewComment(BaseModel):
    path: str
    line: int
    body: str
    suggestion: str | None = Field(
        default=None,
        description="Exact replacement code for this line, if a concrete fix applies.",
    )


class ReviewResult(BaseModel):
    summary: str
    comments: list[ReviewComment] = Field(default_factory=list)


# --- LLM output: debug diagnosis -------------------------------------------

class DebugIssue(BaseModel):
    file: str
    line: int
    problem: str
    fix: str
    patch: str | None = Field(
        default=None,
        description="Concrete replacement code implementing the fix, if applicable.",
    )


class DebugResult(BaseModel):
    root_cause_summary: str
    issues: list[DebugIssue] = Field(default_factory=list)
