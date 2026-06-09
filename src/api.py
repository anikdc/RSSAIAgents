import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.orchestrator import Orchestrator
from src.persistence import get_persistence
from src.secrets_helper import load_secrets


load_secrets()
os.environ.setdefault("SENTENCE_TRANSFORMERS_LOCAL_ONLY", "true")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

app = FastAPI(title="AI News Trend Worker API", version="0.1.0")
executor = ThreadPoolExecutor(max_workers=int(os.getenv("PYTHON_WORKER_MAX_JOBS", "2")))
store = get_persistence()


def now():
    return datetime.now().isoformat()


class BriefingJobRequest(BaseModel):
    algorithm: Literal["hdbscan", "dbscan", "kmeans"] = "hdbscan"
    skip_fetch: bool = False
    time_window_hours: float = Field(default=24.0, gt=0, le=168)


class SearchJobRequest(BaseModel):
    query: str = Field(min_length=1)
    algorithm: Literal["hdbscan", "dbscan", "kmeans"] = "hdbscan"


@app.get("/")
def root():
    return {
        "service": "AI News Trend Worker API",
        "health": "/health",
        "docs": "/docs",
        "latest_briefing": "/briefings/latest",
    }


def create_job(kind, payload):
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "kind": kind,
        "status": "queued",
        "phase": "queued",
        "payload": payload,
        "events": [{"phase": "queued", "timestamp": now()}],
        "created_at": now(),
        "updated_at": now(),
    }
    return store.upsert_job(job)


def update_job(job_id, **updates):
    job = store.get_job(job_id)
    if not job:
        return None
    job.update(updates)
    return store.upsert_job(job)


def run_job(job_id, kind, payload):
    def progress(event):
        store.append_job_event(job_id, event)

    update_job(job_id, status="running", phase="started", started_at=now())
    progress({"phase": "started", "timestamp": now()})

    try:
        orchestrator = Orchestrator()
        if kind == "search":
            result = orchestrator.run_search_pipeline(
                payload["query"],
                algorithm=payload["algorithm"],
                write_output=True,
                progress_callback=progress,
            )
        else:
            result = orchestrator.run_pipeline(
                algorithm=payload["algorithm"],
                skip_fetch=payload["skip_fetch"],
                time_window_hours=payload["time_window_hours"],
                write_output=True,
                progress_callback=progress,
            )

        if result.get("status") == "complete":
            store.save_briefing(result)
        update_job(
            job_id,
            status=result.get("status", "complete"),
            phase=result.get("status", "complete"),
            result=result,
            completed_at=now(),
        )
    except Exception as exc:
        progress({"phase": "failed", "timestamp": now(), "error": str(exc)})
        update_job(job_id, status="failed", phase="failed", error=str(exc), completed_at=now())


def submit_job(kind, payload):
    job = create_job(kind, payload)
    executor.submit(run_job, job["id"], kind, payload)
    return job


@app.get("/health")
def health():
    return {
        "status": "ok",
        "persistence": getattr(store, "kind", "unknown"),
    }


@app.post("/jobs/briefing")
def start_briefing_job(request: BriefingJobRequest):
    return submit_job("briefing", request.model_dump())


@app.post("/jobs/search")
def start_search_job(request: SearchJobRequest):
    return submit_job("search", request.model_dump())


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/briefings/latest")
def get_latest_briefing():
    briefing = store.get_latest_briefing()
    if not briefing:
        raise HTTPException(status_code=404, detail="No briefing has been generated yet")
    return briefing
