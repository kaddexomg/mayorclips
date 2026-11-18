import os
import sys
import json
from pathlib import Path

# Ensure both project root and backend dir are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select, func
from pydantic import BaseModel

from app.config import (
    BACKEND_PORT, STORAGE_DIR, RENDERS_DIR, MEDIA_DIR,
    GEMINI_API_KEYS, GOOGLE_CLIENT_ID
)
from app.db import init_db, get_session, engine
from app.models import (
    Project, Moment, Clip, StudioVideo, Job,
    SocialAccount, Post, PostTarget, PostMetric, PulpoUsage
)
from app.jobs import enqueue_job, register_ws_client, unregister_ws_client, update_job_status
from pulpo import pulpo, gemini_pool
from clipper.pipeline import process_project_pipeline, render_single_clip_job
from publisher.stats.collector import update_all_metrics_job
from higgsfield import higgsfield_connector, VideoGenerationRequest

app = FastAPI(
    title="MayorClips API",
    description="Motor de Clipping IA, Videos Motion Graphics y Publicador Multi-Red",
    version="1.0.0"
)

# CORS enabled for local Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount storage for direct video and audio streaming
app.mount("/renders", StaticFiles(directory=str(RENDERS_DIR)), name="renders")
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")

@app.on_event("startup")
def on_startup():
    init_db()

# --- Health & Status ---
@app.get("/health")
def health_check():
    return {"status": "ok", "app": "MayorClips", "version": "1.0.0"}

@app.get("/pulpo/status")
def get_pulpo_status(session: Session = Depends(get_session)):
    keys_stats = []
    for k in gemini_pool.keys:
        prefix = k[:10] + "..."
        is_dead = k in gemini_pool.dead_keys
        cd = gemini_pool.cooldowns.get(k, 0)
        st = gemini_pool.stats.get(k, {})
        keys_stats.append({
            "key_prefix": prefix,
            "status": "dead" if is_dead else ("cooldown" if cd > 0 else "active"),
            "calls": st.get("calls", 0),
            "errors": st.get("errors", 0),
            "tokens": st.get("tokens", 0)
        })
    
    total_calls = session.exec(select(func.count(PulpoUsage.id))).one()
    total_tokens = session.exec(select(func.sum(PulpoUsage.input_tokens + PulpoUsage.output_tokens))).one() or 0

    return {
        "active_models": ["gemini-3-flash-preview", "gemini-3.1-flash-lite"],
        "total_keys": len(gemini_pool.keys),
        "keys": keys_stats,
        "total_api_calls": total_calls,
        "total_tokens_used": total_tokens
    }

# --- Projects ---
class CreateProjectPayload(BaseModel):
    url: str
    title: Optional[str] = "Nueva Transmisión"
    source_type: Optional[str] = "youtube"

@app.post("/projects", response_model=Project)
def create_project(payload: CreateProjectPayload, session: Session = Depends(get_session)):
    proj = Project(
        title=payload.title or "Nueva Transmisión",
        source_url=payload.url,
        source_type=payload.source_type,
        status="pending"
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return proj

@app.get("/projects", response_model=List[Project])
def list_projects(session: Session = Depends(get_session)):
    return session.exec(select(Project).order_by(Project.created_at.desc())).all()

@app.get("/projects/{project_id}", response_model=Project)
def get_project(project_id: str, session: Session = Depends(get_session)):
    proj = session.get(Project, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return proj

@app.post("/projects/{project_id}/analyze")
def trigger_project_analysis(project_id: str, session: Session = Depends(get_session)):
    proj = session.get(Project, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")

    async def _task(job_id: str):
        def cb(progress: int, msg: str):
            update_job_status(job_id, status="running", progress=progress, message=msg)
        return await process_project_pipeline(job_id, project_id, progress_callback=cb)

    job = enqueue_job(job_type="analyze", target_id=project_id, task_func=_task)
    return {"message": "Análisis encolado en el pipeline de IA", "job_id": job.id}

@app.get("/projects/{project_id}/moments", response_model=List[Moment])
def list_project_moments(project_id: str, session: Session = Depends(get_session)):
    return session.exec(
        select(Moment).where(Moment.project_id == project_id).order_by(Moment.virality_score.desc())
    ).all()

# --- Clips ---
class CreateClipPayload(BaseModel):
    project_id: str
    moment_id: Optional[str] = None
    title: str = "Clip Viral"
    hook_text: Optional[str] = ""
    event_comment: Optional[str] = None
    start_sec: float
    end_sec: float
    layout: Optional[str] = "split_screen"
    subtitle_style: Optional[str] = "hormozi"

@app.post("/clips", response_model=Clip)
def create_clip(payload: CreateClipPayload, session: Session = Depends(get_session)):
    dur = round(max(1.0, payload.end_sec - payload.start_sec), 2)
    clip = Clip(
        project_id=payload.project_id,
        moment_id=payload.moment_id,
        title=payload.title,
        hook_text=payload.hook_text or payload.title,
        event_comment=payload.event_comment,
        start_sec=payload.start_sec,
        end_sec=payload.end_sec,
        duration_sec=dur,
        layout=payload.layout or "split_screen",
        subtitle_style=payload.subtitle_style or "hormozi",
        status="draft"
    )
    session.add(clip)
    session.commit()
    session.refresh(clip)
    return clip

@app.get("/clips", response_model=List[Clip])
def list_clips(project_id: Optional[str] = None, session: Session = Depends(get_session)):
    q = select(Clip)
    if project_id:
        q = q.where(Clip.project_id == project_id)
    return session.exec(q.order_by(Clip.created_at.desc())).all()

@app.get("/clips/{clip_id}", response_model=Clip)
def get_clip(clip_id: str, session: Session = Depends(get_session)):
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    return clip

class UpdateClipPayload(BaseModel):
    title: Optional[str] = None
    hook_text: Optional[str] = None
    event_comment: Optional[str] = None
    layout: Optional[str] = None
    subtitle_style: Optional[str] = None

@app.patch("/clips/{clip_id}", response_model=Clip)
def update_clip(clip_id: str, payload: UpdateClipPayload, session: Session = Depends(get_session)):
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    if payload.title is not None: clip.title = payload.title
    if payload.hook_text is not None: clip.hook_text = payload.hook_text
    if payload.event_comment is not None: clip.event_comment = payload.event_comment
    if payload.layout is not None: clip.layout = payload.layout
    if payload.subtitle_style is not None: clip.subtitle_style = payload.subtitle_style
    session.add(clip)
    session.commit()
    session.refresh(clip)
    return clip

@app.post("/clips/{clip_id}/render")
def trigger_clip_render(clip_id: str, session: Session = Depends(get_session)):
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")

    async def _task(job_id: str):
        def cb(prog: int, msg: str):
            update_job_status(job_id, status="running", progress=prog, message=msg)
        return await render_single_clip_job(job_id, clip_id, progress_callback=cb)

    job = enqueue_job(job_type="render_clip", target_id=clip_id, task_func=_task)
    return {"message": "Renderizado de clip vertical encolado", "job_id": job.id}

# --- Studio Motion Graphics (Fase 2 endpoints) ---
class CreateStudioPayload(BaseModel):
    topic: str
    style: Optional[str] = "curiosities"

@app.post("/studio")
async def create_studio_video(payload: CreateStudioPayload, session: Session = Depends(get_session)):
    # Pulpo generates script and scene plan
    script = await pulpo.run("script", {"topic": payload.topic, "style": payload.style})
    scene_plan = await pulpo.run("scene_plan", {"script": script})
    
    studio_item = StudioVideo(
        title=script.get("title", "Video Motion Graphics"),
        topic=payload.topic,
        style=payload.style,
        script_json=script,
        scene_plan_json=scene_plan,
        status="draft"
    )
    session.add(studio_item)
    session.commit()
    session.refresh(studio_item)
    return studio_item

@app.get("/studio", response_model=List[StudioVideo])
def list_studio_videos(session: Session = Depends(get_session)):
    return session.exec(select(StudioVideo).order_by(StudioVideo.created_at.desc())).all()

# --- Social Accounts & Publishing ---
@app.get("/accounts", response_model=List[SocialAccount])
def list_accounts(session: Session = Depends(get_session)):
    return session.exec(select(SocialAccount)).all()

class ConnectAccountPayload(BaseModel):
    platform: str
    account_name: str
    account_id: str
    access_token: str

@app.post("/accounts", response_model=SocialAccount)
def connect_account(payload: ConnectAccountPayload, session: Session = Depends(get_session)):
    acc = SocialAccount(
        platform=payload.platform,
        account_name=payload.account_name,
        account_id=payload.account_id,
        access_token_enc=payload.access_token,
        status="active"
    )
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return acc

class CreatePostPayload(BaseModel):
    media_id: str
    media_type: Optional[str] = "clip"
    caption: str
    platforms: List[str] # ["instagram", "facebook", "tiktok"]

@app.post("/posts", response_model=Post)
def create_post(payload: CreatePostPayload, session: Session = Depends(get_session)):
    post = Post(
        media_id=payload.media_id,
        media_type=payload.media_type,
        caption_base=payload.caption,
        platforms_json=payload.platforms,
        status="draft"
    )
    session.add(post)
    session.commit()
    session.refresh(post)

    for p in payload.platforms:
        target = PostTarget(
            post_id=post.id,
            platform=p,
            status="pending"
        )
        session.add(target)
    session.commit()
    return post

@app.get("/posts", response_model=List[Post])
def list_posts(session: Session = Depends(get_session)):
    return session.exec(select(Post).order_by(Post.created_at.desc())).all()

# --- Statistics & Metrics Dashboard ---
@app.get("/stats/summary")
def get_stats_summary(session: Session = Depends(get_session)):
    total_clips = session.exec(select(func.count(Clip.id))).one()
    total_projects = session.exec(select(func.count(Project.id))).one()
    total_posts = session.exec(select(func.count(Post.id))).one()
    
    total_views = session.exec(select(func.sum(PostMetric.views))).one() or 0
    total_likes = session.exec(select(func.sum(PostMetric.likes))).one() or 0
    total_shares = session.exec(select(func.sum(PostMetric.shares))).one() or 0

    return {
        "total_projects": total_projects,
        "total_clips": total_clips,
        "total_posts": total_posts,
        "metrics": {
            "views": total_views,
            "likes": total_likes,
            "shares": total_shares
        },
        "platforms": {
            "instagram": {"views": int(total_views * 0.45), "active": True},
            "facebook": {"views": int(total_views * 0.25), "active": True},
            "tiktok": {"views": int(total_views * 0.30), "active": True}
        }
    }

# --- Higgsfield / Cinematic B-Roll Studio ---
@app.get("/higgsfield/status")
def get_higgsfield_status():
    return {
        "has_subscription": higgsfield_connector.has_subscription,
        "mode": "official-mcp" if higgsfield_connector.has_subscription else "open-alternative-cloud",
        "supported_motions": ["pan_left", "pan_right", "tilt_up", "tilt_down", "zoom_in", "zoom_out", "orbit_3d"]
    }

@app.post("/higgsfield/generate-broll")
async def generate_higgsfield_broll(req: VideoGenerationRequest):
    try:
        return await higgsfield_connector.generate_cinematic_broll(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- WebSocket for Realtime Job Progress ---
@app.websocket("/ws/jobs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    register_ws_client(websocket)
    try:
        while True:
            # Keepalive listener
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        unregister_ws_client(websocket)
    except Exception:
        unregister_ws_client(websocket)
