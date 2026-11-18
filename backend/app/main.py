import os
import sys
import json
import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

# Ensure both project root and backend dir are in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select, func
from pydantic import BaseModel
import httpx

from app.config import (
    BACKEND_PORT, STORAGE_DIR, RENDERS_DIR, MEDIA_DIR,
    GEMINI_API_KEYS, GOOGLE_CLIENT_ID, META_APP_ID, META_APP_SECRET,
    TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET
)
from app.db import init_db, get_session, engine
from app.models import (
    Project, Moment, Clip, StudioVideo, Job,
    SocialAccount, Post, PostTarget, PostMetric, PulpoUsage, Transcript
)
from app.jobs import (
    enqueue_job, register_ws_client, unregister_ws_client,
    update_job_status, set_main_loop
)
from pulpo import pulpo, gemini_pool
from clipper.pipeline import process_project_pipeline, render_single_clip_job
from studio.generator import render_studio_video_job
from publisher.uploaders.meta import meta_publisher
from publisher.uploaders.tiktok import tiktok_publisher
from publisher.stats.collector import update_all_metrics_job
from higgsfield import higgsfield_connector, VideoGenerationRequest

app = FastAPI(
    title="MayorClips API",
    description="Motor de Clipping IA, Videos Motion Graphics y Publicador Multi-Red",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Guarantees structured JSON + CORS headers even on unexpected exceptions (prevents Failed to fetch)."""
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={"Access-Control-Allow-Origin": "*"},
    )


app.mount("/renders", StaticFiles(directory=str(RENDERS_DIR)), name="renders")
app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")


@app.on_event("startup")
async def on_startup():
    init_db()
    set_main_loop(asyncio.get_running_loop())
    from clipper.transcriber import preload_whisper_model
    asyncio.create_task(asyncio.to_thread(preload_whisper_model))


def _clip_with_urls(clip: Clip) -> Dict[str, Any]:
    d = clip.model_dump()
    d["video_url"] = f"/renders/{Path(clip.output_path).name}" if clip.output_path and Path(clip.output_path).exists() else None
    d["thumbnail_url"] = f"/renders/{Path(clip.thumbnail_path).name}" if clip.thumbnail_path and Path(clip.thumbnail_path).exists() else None
    return d


# --- Health & Status ---
@app.get("/health")
def health_check():
    return {"status": "ok", "app": "MayorClips", "version": "1.2.0"}


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
            "tokens": st.get("tokens", 0),
        })

    total_calls = session.exec(select(func.count(PulpoUsage.id))).one()
    total_tokens = session.exec(select(func.sum(PulpoUsage.input_tokens + PulpoUsage.output_tokens))).one() or 0

    return {
        "active_models": ["gemini-3-flash-preview", "gemini-flash-lite-latest", "gemini-3.1-flash-lite"],
        "total_keys": len(gemini_pool.keys),
        "keys": keys_stats,
        "total_api_calls": total_calls,
        "total_tokens_used": total_tokens,
    }


class WriteTitlesPayload(BaseModel):
    summary: str
    hook: Optional[str] = ""


@app.post("/pulpo/write-titles")
async def pulpo_write_titles(payload: WriteTitlesPayload):
    return await pulpo.run("write_titles", {"summary": payload.summary, "hook": payload.hook or ""})


# --- Jobs ---
@app.get("/jobs/{job_id}", response_model=Job)
def get_job_status(job_id: str, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return job


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
        status="pending",
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return proj


@app.post("/projects/upload", response_model=Project)
async def upload_local_project(
    file: UploadFile = File(...),
    title: str = Form("Video Local"),
    session: Session = Depends(get_session),
):
    safe_name = f"local_{os.urandom(4).hex()}_{Path(file.filename).name}"
    dest = MEDIA_DIR / safe_name
    with open(dest, "wb") as out_f:
        shutil.copyfileobj(file.file, out_f)

    proj = Project(
        title=title or Path(file.filename).stem,
        source_type="file",
        source_url=str(dest),
        video_path=str(dest),
        status="pending",
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


@app.delete("/projects/{project_id}")
def delete_project(project_id: str, session: Session = Depends(get_session)):
    proj = session.get(Project, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    for m in session.exec(select(Moment).where(Moment.project_id == project_id)).all():
        session.delete(m)
    for c in session.exec(select(Clip).where(Clip.project_id == project_id)).all():
        session.delete(c)
    session.delete(proj)
    session.commit()
    return {"deleted": True}


@app.post("/projects/{project_id}/analyze")
async def trigger_project_analysis(project_id: str, session: Session = Depends(get_session)):
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


@app.get("/projects/{project_id}/transcript")
def get_project_transcript(project_id: str, session: Session = Depends(get_session)):
    tr = session.exec(select(Transcript).where(Transcript.project_id == project_id)).first()
    return {"full_text": tr.full_text if tr else ""}


# --- Clips ---
class CreateClipPayload(BaseModel):
    project_id: str
    moment_id: Optional[str] = None
    title: str = "Clip Viral"
    hook_text: Optional[str] = ""
    event_comment: Optional[str] = None
    start_sec: float
    end_sec: float
    layout: Optional[str] = "auto"
    content_mode: Optional[str] = "auto"
    hook_persistence: Optional[str] = "intro"
    show_subtitles: Optional[bool] = True
    video_transitions: Optional[bool] = True
    subtitle_style: Optional[str] = "hormozi"


@app.post("/clips")
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
        layout=payload.layout or "auto",
        content_mode=payload.content_mode or "auto",
        hook_persistence=payload.hook_persistence or "intro",
        show_subtitles=True if payload.show_subtitles is None else payload.show_subtitles,
        video_transitions=True if payload.video_transitions is None else payload.video_transitions,
        subtitle_style=payload.subtitle_style or "hormozi",
        status="draft",
    )
    session.add(clip)
    session.commit()
    session.refresh(clip)
    return _clip_with_urls(clip)


@app.get("/clips")
def list_clips(project_id: Optional[str] = None, session: Session = Depends(get_session)):
    q = select(Clip)
    if project_id:
        q = q.where(Clip.project_id == project_id)
    rows = session.exec(q.order_by(Clip.created_at.desc())).all()
    return [_clip_with_urls(c) for c in rows]


@app.get("/clips/{clip_id}")
def get_clip(clip_id: str, session: Session = Depends(get_session)):
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    return _clip_with_urls(clip)


class UpdateClipPayload(BaseModel):
    title: Optional[str] = None
    hook_text: Optional[str] = None
    event_comment: Optional[str] = None
    layout: Optional[str] = None
    content_mode: Optional[str] = None
    hook_persistence: Optional[str] = None
    show_subtitles: Optional[bool] = None
    video_transitions: Optional[bool] = None
    subtitle_style: Optional[str] = None
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None


@app.patch("/clips/{clip_id}")
def update_clip(clip_id: str, payload: UpdateClipPayload, session: Session = Depends(get_session)):
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    if payload.title is not None: clip.title = payload.title
    if payload.hook_text is not None: clip.hook_text = payload.hook_text
    if payload.event_comment is not None: clip.event_comment = payload.event_comment
    if payload.layout is not None: clip.layout = payload.layout
    if payload.content_mode is not None: clip.content_mode = payload.content_mode
    if payload.hook_persistence is not None: clip.hook_persistence = payload.hook_persistence
    if payload.show_subtitles is not None: clip.show_subtitles = payload.show_subtitles
    if payload.video_transitions is not None: clip.video_transitions = payload.video_transitions
    if payload.subtitle_style is not None: clip.subtitle_style = payload.subtitle_style
    if payload.start_sec is not None: clip.start_sec = payload.start_sec
    if payload.end_sec is not None: clip.end_sec = payload.end_sec
    clip.duration_sec = round(max(1.0, clip.end_sec - clip.start_sec), 2)
    clip.updated_at = datetime.now(timezone.utc)
    session.add(clip)
    session.commit()
    session.refresh(clip)
    return _clip_with_urls(clip)


@app.delete("/clips/{clip_id}")
def delete_clip(clip_id: str, session: Session = Depends(get_session)):
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    if clip.output_path and Path(clip.output_path).exists():
        try:
            Path(clip.output_path).unlink()
        except Exception:
            pass
    session.delete(clip)
    session.commit()
    return {"deleted": True}


@app.post("/clips/{clip_id}/render")
async def trigger_clip_render(clip_id: str, session: Session = Depends(get_session)):
    clip = session.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")

    async def _task(job_id: str):
        def cb(prog: int, msg: str):
            update_job_status(job_id, status="running", progress=prog, message=msg)
        return await render_single_clip_job(job_id, clip_id, progress_callback=cb)

    job = enqueue_job(job_type="render_clip", target_id=clip_id, task_func=_task)
    return {"message": "Renderizado de clip vertical encolado", "job_id": job.id}


# --- Studio Motion Graphics ---
class CreateStudioPayload(BaseModel):
    topic: str
    style: Optional[str] = "curiosities"
    voice_name: Optional[str] = "es-MX-DaliaNeural"


def _studio_with_urls(sv: StudioVideo) -> Dict[str, Any]:
    d = sv.model_dump()
    d["video_url"] = f"/renders/{Path(sv.output_path).name}" if sv.output_path and Path(sv.output_path).exists() else None
    hf_dir = STORAGE_DIR / "studio_hf" / sv.id
    d["hf_project_dir"] = str(hf_dir) if (hf_dir / "index.html").exists() else None
    return d


@app.post("/studio")
async def create_studio_video(payload: CreateStudioPayload, session: Session = Depends(get_session)):
    script = await pulpo.run("script", {"topic": payload.topic, "style": payload.style})
    scene_plan = await pulpo.run("scene_plan", {"script": script})

    studio_item = StudioVideo(
        title=script.get("title", "Video Motion Graphics"),
        topic=payload.topic,
        style=payload.style or "curiosities",
        voice_name=payload.voice_name or "es-MX-DaliaNeural",
        script_json=script,
        scene_plan_json=scene_plan,
        status="draft",
    )
    session.add(studio_item)
    session.commit()
    session.refresh(studio_item)
    return _studio_with_urls(studio_item)


@app.post("/studio/{studio_id}/render")
async def trigger_studio_render(studio_id: str, session: Session = Depends(get_session)):
    sv = session.get(StudioVideo, studio_id)
    if not sv:
        raise HTTPException(status_code=404, detail="Proyecto Studio no encontrado")

    async def _task(job_id: str):
        def cb(prog: int, msg: str):
            update_job_status(job_id, status="running", progress=prog, message=msg)
        return await render_studio_video_job(job_id, studio_id, progress_callback=cb)

    job = enqueue_job(job_type="studio_render", target_id=studio_id, task_func=_task)
    return {"message": "Renderizado Motion Graphics encolado", "job_id": job.id}


@app.get("/studio")
def list_studio_videos(session: Session = Depends(get_session)):
    items = session.exec(select(StudioVideo).order_by(StudioVideo.created_at.desc())).all()
    return [_studio_with_urls(sv) for sv in items]


# --- Social Accounts & Real OAuth ---
@app.get("/accounts")
def list_accounts(session: Session = Depends(get_session)):
    accs = session.exec(select(SocialAccount)).all()
    return [
        {
            "id": a.id,
            "platform": a.platform,
            "account_name": a.account_name,
            "account_id": a.account_id,
            "status": a.status,
            "created_at": a.created_at,
        }
        for a in accs
    ]


@app.get("/oauth/config-status")
def get_oauth_config_status():
    return {
        "meta_configured": bool(META_APP_ID and META_APP_SECRET),
        "tiktok_configured": bool(TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET),
        "google_configured": bool(GOOGLE_CLIENT_ID),
        "vps_public_base": os.getenv("VPS_PUBLIC_BASE_URL", ""),
    }


@app.get("/oauth/meta/start")
def oauth_meta_start():
    if not META_APP_ID:
        raise HTTPException(status_code=400, detail="META_APP_ID no configurado en .env. Usa la verificación directa con Token o configura tu App ID de Meta for Developers.")
    redirect_uri = os.getenv("META_REDIRECT_URI") or f"http://127.0.0.1:{BACKEND_PORT}/oauth/meta/callback"
    params = urlencode({
        "client_id": META_APP_ID,
        "redirect_uri": redirect_uri,
        "scope": "pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish",
        "response_type": "code",
    })
    return {"auth_url": f"https://www.facebook.com/v21.0/dialog/oauth?{params}"}


@app.get("/oauth/meta/callback")
async def oauth_meta_callback(code: str, session: Session = Depends(get_session)):
    redirect_uri = os.getenv("META_REDIRECT_URI") or f"http://127.0.0.1:{BACKEND_PORT}/oauth/meta/callback"
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={"client_id": META_APP_ID, "client_secret": META_APP_SECRET, "redirect_uri": redirect_uri, "code": code},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Error Meta OAuth: {r.text}")
        token = r.json().get("access_token")

    pages = await meta_publisher.discover_pages_and_ig(token)
    saved = _save_meta_pages(session, pages)
    return {"connected": len(saved), "accounts": saved}


def _save_meta_pages(session: Session, pages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    saved = []
    for p in pages:
        page_id = str(p["id"])
        page_name = p.get("name", "Página Facebook")
        page_token = p.get("access_token", "")
        if not page_token:
            continue

        existing_fb = session.exec(select(SocialAccount).where(SocialAccount.platform == "facebook", SocialAccount.account_id == page_id)).first()
        if existing_fb:
            existing_fb.access_token_enc = page_token
            existing_fb.account_name = page_name
            existing_fb.status = "active"
            session.add(existing_fb)
        else:
            session.add(SocialAccount(platform="facebook", account_name=page_name, account_id=page_id, access_token_enc=page_token, status="active"))
        saved.append({"platform": "facebook", "account_name": page_name, "account_id": page_id})

        ig = p.get("instagram_business_account")
        if ig and ig.get("id"):
            ig_id = str(ig["id"])
            ig_user = f"@{ig.get('username', page_name)}"
            existing_ig = session.exec(select(SocialAccount).where(SocialAccount.platform == "instagram", SocialAccount.account_id == ig_id)).first()
            if existing_ig:
                existing_ig.access_token_enc = page_token
                existing_ig.account_name = ig_user
                existing_ig.status = "active"
                session.add(existing_ig)
            else:
                session.add(SocialAccount(platform="instagram", account_name=ig_user, account_id=ig_id, access_token_enc=page_token, status="active"))
            saved.append({"platform": "instagram", "account_name": ig_user, "account_id": ig_id})
    session.commit()
    return saved


class VerifyTokenPayload(BaseModel):
    access_token: str


@app.post("/accounts/verify-meta")
async def verify_and_connect_meta(payload: VerifyTokenPayload, session: Session = Depends(get_session)):
    pages = await meta_publisher.discover_pages_and_ig(payload.access_token.strip())
    if not pages:
        raise HTTPException(status_code=400, detail="No se encontraron Páginas de Facebook o cuentas de Instagram Business asociadas a este token.")
    saved = _save_meta_pages(session, pages)
    return {"connected": len(saved), "accounts": saved}


@app.post("/accounts/verify-tiktok")
async def verify_and_connect_tiktok(payload: VerifyTokenPayload, session: Session = Depends(get_session)):
    user = await tiktok_publisher.verify_token(payload.access_token.strip())
    open_id = str(user.get("open_id", "tiktok_user"))
    name = user.get("display_name", "Cuenta TikTok")
    existing = session.exec(select(SocialAccount).where(SocialAccount.platform == "tiktok", SocialAccount.account_id == open_id)).first()
    if existing:
        existing.access_token_enc = payload.access_token.strip()
        existing.account_name = name
        existing.status = "active"
        session.add(existing)
    else:
        session.add(SocialAccount(platform="tiktok", account_name=name, account_id=open_id, access_token_enc=payload.access_token.strip(), status="active"))
    session.commit()
    return {"connected": 1, "accounts": [{"platform": "tiktok", "account_name": name, "account_id": open_id}]}


@app.delete("/accounts/{account_id}")
def delete_account(account_id: str, session: Session = Depends(get_session)):
    acc = session.get(SocialAccount, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    session.delete(acc)
    session.commit()
    return {"deleted": True}


# --- Publishing ---
class CreatePostPayload(BaseModel):
    media_id: str
    media_type: Optional[str] = "clip"
    caption: str
    platforms: List[str]


@app.post("/posts")
async def create_and_publish_post(payload: CreatePostPayload, session: Session = Depends(get_session)):
    # Locate rendered local MP4 file
    media_path = None
    if payload.media_type == "studio_video":
        sv = session.get(StudioVideo, payload.media_id)
        if sv and sv.output_path and Path(sv.output_path).exists():
            media_path = sv.output_path
    else:
        clip = session.get(Clip, payload.media_id)
        if clip and clip.output_path and Path(clip.output_path).exists():
            media_path = clip.output_path

    if not media_path:
        raise HTTPException(status_code=400, detail="El clip seleccionado no tiene un video MP4 renderizado todavía. Renderízalo primero.")

    post = Post(
        media_id=payload.media_id,
        media_type=payload.media_type or "clip",
        caption_base=payload.caption,
        platforms_json=payload.platforms,
        status="publishing",
    )
    session.add(post)
    session.commit()
    session.refresh(post)

    results = []
    vps_public_base = os.getenv("VPS_PUBLIC_BASE_URL", "").rstrip("/")
    video_public_url = f"{vps_public_base}/mc-media/{Path(media_path).name}" if vps_public_base else ""

    for plat in payload.platforms:
        acc = session.exec(select(SocialAccount).where(SocialAccount.platform == plat, SocialAccount.status == "active")).first()
        target = PostTarget(post_id=post.id, platform=plat, status="pending")

        if not acc:
            target.status = "failed"
            target.error_message = f"No hay ninguna cuenta de {plat} conectada. Ve a la pestaña Cuentas para vincularla."
        else:
            try:
                if plat == "facebook":
                    res = await meta_publisher.publish_facebook_reel_file(acc.account_id, acc.access_token_enc, media_path, payload.caption)
                    target.status = "published"
                    target.remote_post_id = res.get("remote_id")
                    target.published_at = datetime.now(timezone.utc)
                elif plat == "tiktok":
                    res = await tiktok_publisher.upload_file_to_inbox(acc.access_token_enc, media_path)
                    target.status = "draft_inbox"
                    target.remote_post_id = res.get("remote_id")
                    target.published_at = datetime.now(timezone.utc)
                elif plat == "instagram":
                    res = await meta_publisher.publish_instagram_reel(acc.account_id, acc.access_token_enc, video_public_url, payload.caption)
                    target.status = "published"
                    target.remote_post_id = res.get("remote_id")
                    target.published_at = datetime.now(timezone.utc)
                else:
                    target.status = "failed"
                    target.error_message = f"Plataforma {plat} aún en desarrollo."
            except Exception as pub_err:
                target.status = "failed"
                target.error_message = str(pub_err)

        session.add(target)
        session.commit()
        session.refresh(target)
        results.append(target.model_dump())

    any_ok = any(r["status"] in ("published", "draft_inbox") for r in results)
    post.status = "published" if any_ok else "failed"
    session.add(post)
    session.commit()
    session.refresh(post)

    return {"post": post.model_dump(), "targets": results}


@app.get("/posts")
def list_posts(session: Session = Depends(get_session)):
    posts = session.exec(select(Post).order_by(Post.created_at.desc())).all()
    out = []
    for p in posts:
        targets = session.exec(select(PostTarget).where(PostTarget.post_id == p.id)).all()
        d = p.model_dump()
        d["targets"] = [t.model_dump() for t in targets]
        out.append(d)
    return out


# --- Statistics & Metrics Dashboard (100% Real Data) ---
@app.get("/stats/summary")
def get_stats_summary(session: Session = Depends(get_session)):
    total_clips = session.exec(select(func.count(Clip.id))).one()
    ready_clips = session.exec(select(func.count(Clip.id)).where(Clip.status == "ready")).one()
    total_projects = session.exec(select(func.count(Project.id))).one()
    total_posts = session.exec(select(func.count(Post.id))).one()

    total_views = session.exec(select(func.sum(PostMetric.views))).one() or 0
    total_likes = session.exec(select(func.sum(PostMetric.likes))).one() or 0
    total_shares = session.exec(select(func.sum(PostMetric.shares))).one() or 0

    ig_views = session.exec(select(func.sum(PostMetric.views)).where(PostMetric.platform == "instagram")).one() or 0
    fb_views = session.exec(select(func.sum(PostMetric.views)).where(PostMetric.platform == "facebook")).one() or 0
    tt_views = session.exec(select(func.sum(PostMetric.views)).where(PostMetric.platform == "tiktok")).one() or 0

    return {
        "total_projects": total_projects,
        "total_clips": total_clips,
        "ready_clips": ready_clips,
        "total_posts": total_posts,
        "metrics": {
            "views": total_views,
            "likes": total_likes,
            "shares": total_shares,
        },
        "platforms": {
            "instagram": {"views": ig_views},
            "facebook": {"views": fb_views},
            "tiktok": {"views": tt_views},
        },
    }


# --- Higgsfield / Cinematic B-Roll Studio ---
@app.get("/higgsfield/status")
def get_higgsfield_status():
    return {
        "has_subscription": higgsfield_connector.has_subscription,
        "mode": "official-mcp" if higgsfield_connector.has_subscription else "open-alternative-cloud",
        "supported_motions": ["pan_left", "pan_right", "tilt_up", "tilt_down", "zoom_in", "zoom_out", "orbit_3d"],
    }


@app.post("/higgsfield/generate-broll")
async def generate_higgsfield_broll(req: VideoGenerationRequest):
    return await higgsfield_connector.generate_cinematic_broll(req)


# --- WebSocket for Realtime Job Progress ---
@app.websocket("/ws/jobs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    register_ws_client(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        unregister_ws_client(websocket)
    except Exception:
        unregister_ws_client(websocket)
