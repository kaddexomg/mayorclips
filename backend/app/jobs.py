import asyncio
import traceback
from datetime import datetime, timezone
from typing import Callable, Coroutine, Any, Dict
from sqlmodel import Session, select
from app.db import engine
from app.models import Job

# Single worker semaphore: only 1 heavy job at a time to strictly safeguard 7.3GB RAM
MAX_CONCURRENCY = 1
_semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
_active_jobs: Dict[str, asyncio.Task] = {}
_ws_clients: set = set()

def register_ws_client(ws):
    _ws_clients.add(ws)

def unregister_ws_client(ws):
    _ws_clients.discard(ws)

async def broadcast_job_update(job_data: dict):
    if not _ws_clients:
        return
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_json(job_data)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _ws_clients.discard(ws)

def update_job_status(job_id: str, status: str, progress: int = None, message: str = None, result: dict = None, error: str = None):
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job:
            return
        job.status = status
        if progress is not None:
            job.progress = progress
        if message is not None:
            job.message = message
        if result is not None:
            job.result_json = result
        if error is not None:
            job.error_message = error
        job.updated_at = datetime.now(timezone.utc)
        session.add(job)
        session.commit()
        session.refresh(job)

        # Notify via async loop
        payload = {
            "type": "job_update",
            "job_id": job.id,
            "job_type": job.job_type,
            "target_id": job.target_id,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "result": job.result_json,
            "error": job.error_message
        }
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(broadcast_job_update(payload))
        except RuntimeError:
            pass

async def _worker_wrapper(job_id: str, task_func: Callable[..., Coroutine[Any, Any, Any]], *args, **kwargs):
    async with _semaphore:
        update_job_status(job_id, status="running", progress=5, message="Iniciando procesamiento...")
        try:
            result = await task_func(job_id, *args, **kwargs)
            update_job_status(job_id, status="completed", progress=100, message="Completado exitosamente.", result=result)
        except Exception as e:
            err_msg = f"{str(e)}\n{traceback.format_exc()}"
            print(f"[JOB ERROR] {job_id}: {err_msg}")
            update_job_status(job_id, status="failed", message="Error en la tarea.", error=str(e))
        finally:
            _active_jobs.pop(job_id, None)

def enqueue_job(job_type: str, target_id: str, task_func: Callable[..., Coroutine[Any, Any, Any]], *args, **kwargs) -> Job:
    with Session(engine) as session:
        job = Job(job_type=job_type, target_id=target_id, status="queued", progress=0, message="En cola de espera...")
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    loop = asyncio.get_event_loop()
    task = loop.create_task(_worker_wrapper(job_id, task_func, *args, **kwargs))
    _active_jobs[job_id] = task
    return job
