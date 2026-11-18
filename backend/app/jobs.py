import asyncio
import traceback
from datetime import datetime, timezone
from typing import Callable, Coroutine, Any, Dict, Optional
from sqlmodel import Session
from app.db import engine
from app.models import Job

# Single worker semaphore: only 1 heavy job at a time to strictly safeguard 7.3GB RAM
MAX_CONCURRENCY = 1
_semaphore: Optional[asyncio.Semaphore] = None
_main_loop: Optional[asyncio.AbstractEventLoop] = None
_active_jobs: Dict[str, Any] = {}
_ws_clients: set = set()


def set_main_loop(loop: asyncio.AbstractEventLoop):
    """Stores the FastAPI main event loop at startup so background threads can schedule safely."""
    global _main_loop, _semaphore
    _main_loop = loop
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENCY)


def register_ws_client(ws):
    _ws_clients.add(ws)


def unregister_ws_client(ws):
    _ws_clients.discard(ws)


async def broadcast_job_update(job_data: dict):
    if not _ws_clients:
        return
    dead = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_json(job_data)
        except Exception:
            dead.add(ws)
    for ws in dead:
        _ws_clients.discard(ws)


def update_job_status(
    job_id: str,
    status: str,
    progress: int = None,
    message: str = None,
    result: dict = None,
    error: str = None,
):
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

        payload = {
            "type": "job_update",
            "job_id": job.id,
            "job_type": job.job_type,
            "target_id": job.target_id,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "result": job.result_json,
            "error": job.error_message,
        }

    # Safely notify WebSocket clients from either the main loop or any worker thread
    try:
        running = asyncio.get_running_loop()
        running.create_task(broadcast_job_update(payload))
    except RuntimeError:
        if _main_loop and _main_loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast_job_update(payload), _main_loop)


async def _worker_wrapper(job_id: str, task_func: Callable[..., Coroutine[Any, Any, Any]], *args, **kwargs):
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async with _semaphore:
        update_job_status(job_id, status="running", progress=5, message="Iniciando procesamiento...")
        try:
            result = await task_func(job_id, *args, **kwargs)
            update_job_status(
                job_id,
                status="completed",
                progress=100,
                message="Completado exitosamente.",
                result=result,
            )
        except Exception as e:
            err_msg = f"{str(e)}\n{traceback.format_exc()}"
            print(f"[JOB ERROR] {job_id}: {err_msg}")
            update_job_status(job_id, status="failed", message=f"Error: {str(e)}", error=str(e))
        finally:
            _active_jobs.pop(job_id, None)


def enqueue_job(job_type: str, target_id: str, task_func: Callable[..., Coroutine[Any, Any, Any]], *args, **kwargs) -> Job:
    with Session(engine) as session:
        job = Job(
            job_type=job_type,
            target_id=target_id,
            status="queued",
            progress=0,
            message="En cola de espera...",
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        job_id = job.id

    coro = _worker_wrapper(job_id, task_func, *args, **kwargs)
    try:
        running = asyncio.get_running_loop()
        task = running.create_task(coro)
        _active_jobs[job_id] = task
    except RuntimeError:
        if _main_loop and _main_loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(coro, _main_loop)
            _active_jobs[job_id] = fut
        else:
            raise RuntimeError("El loop principal de asyncio no está inicializado.")
    return job
