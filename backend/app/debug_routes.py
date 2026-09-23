"""
HTTP interface for the PyTorch/CUDA debugging module.

  POST /debug/index     { "repo_path": "..." }
  POST /debug/analyze    { "repo_path": "...", "traceback_text": "..." }
  POST /debug/scan       { "repo_path": "..." }
  GET  /debug/history     -> past scans/analyses, most recent first
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.debug import indexer, analyzer
from app import storage

logger = logging.getLogger("devagent.debug.routes")

router = APIRouter(prefix="/debug")


class IndexRequest(BaseModel):
    repo_path: str


class AnalyzeRequest(BaseModel):
    repo_path: str
    traceback_text: str


class ScanRequest(BaseModel):
    repo_path: str


@router.post("/index")
async def index_repo(req: IndexRequest):
    try:
        result = indexer.index_repo(req.repo_path)
    except Exception as e:
        logger.exception("Indexing failed")
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/analyze")
async def analyze(req: AnalyzeRequest):
    try:
        result = analyzer.analyze_traceback(req.repo_path, req.traceback_text)
    except Exception as e:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=400, detail=str(e))
    storage.save_debug_scan(repo_path=req.repo_path, mode="analyze", result=result)
    return result


@router.post("/scan")
async def scan(req: ScanRequest):
    try:
        result = analyzer.scan_repo(req.repo_path)
    except Exception as e:
        logger.exception("Scan failed")
        raise HTTPException(status_code=400, detail=str(e))
    storage.save_debug_scan(repo_path=req.repo_path, mode="scan", result=result)
    return result


@router.get("/history")
async def history(limit: int = 50):
    return storage.list_debug_scans(limit=limit)