# DevAgent — Step 1: GitHub PR Review Agent

An event-driven agent that listens for GitHub pull request webhooks and posts
an automated code review using a LangGraph pipeline + an LLM.

## How it works

```
GitHub PR opened/updated
        │
        ▼
POST /webhook/github  (FastAPI, verifies HMAC signature)
        │  (background task)
        ▼
LangGraph pipeline:
   fetch_diff  →  analyze (LLM)  →  post_review
        │
        ▼
Review comments posted back to the PR on GitHub
```

- `app/github_webhook.py` — receives + verifies the webhook, filters to
  `opened` / `synchronize` / `reopened` PR events, queues the agent as a
  FastAPI `BackgroundTask` so GitHub gets an instant 200 response.
- `app/agent/nodes.py` — the three pipeline steps as plain async functions.
- `app/agent/graph.py` — wires those steps into a `StateGraph` and exposes
  `run_review_agent()`.

## Setup

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET, OPENAI_API_KEY
```

### GitHub token
Create a fine-grained PAT (or GitHub App) with **Pull requests: Read & Write**
permission on the repo(s) you want DevAgent to review.

### Run locally
```bash
uvicorn app.main:app --reload --port 8000
```

### Expose it to GitHub (local dev)
```bash
ngrok http 8000
```
Then in your repo → Settings → Webhooks → Add webhook:
- Payload URL: `https://<ngrok-id>.ngrok.io/webhook/github`
- Content type: `application/json`
- Secret: same value as `GITHUB_WEBHOOK_SECRET`
- Events: "Pull requests"

Open a PR against the repo — DevAgent should comment with a review within
a few seconds. Check `/health` to confirm the server is up.

## Next steps (later stages of the project)
1. ✅ PR-review agent (this stage)
2. Docker sandbox to actually *run* the code (tests, linters) instead of
   just reading the diff, and feed results back into the review
3. PyTorch/ChromaDB module for GPU/CUDA memory-fragmentation debugging
   and RAG-based fix suggestions
4. Next.js dashboard showing review history, sandbox run logs, etc.
