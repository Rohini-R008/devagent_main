import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.github_webhook import router as webhook_router
from app.debug_routes import router as debug_router
from app.sandbox import runner as sandbox_runner
from app import storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("devagent.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    logger.info("Database ready")

    # Pre-build the sandbox image on startup so the first real PR review
    # doesn't stall on a Docker build. Non-fatal if Docker isn't available
    # yet — run_sandbox() will retry per-request and just skip gracefully.
    try:
        sandbox_runner.ensure_image_built()
        logger.info("Sandbox image ready")
    except Exception as e:  # noqa: BLE001 - startup should never crash the app
        logger.warning("Could not pre-build sandbox image (%s). "
                        "Is Docker Desktop running?", e)
    yield


app = FastAPI(title="DevAgent", version="0.1.0", lifespan=lifespan)

# Allow the local Next.js dev server to call this API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook_router)
app.include_router(debug_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/reviews")
async def reviews(limit: int = 50):
    return storage.list_reviews(limit=limit)