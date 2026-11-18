from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Column, JSON, Text
import uuid

def gen_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: str = Field(default_factory=gen_uuid, primary_key=True)
    title: str = Field(index=True)
    source_type: str = Field(default="youtube", index=True) # twitch, kick, youtube, live, file, faceless
    source_url: Optional[str] = Field(default=None)
    context_hint: Optional[str] = Field(default=None)
    status: str = Field(default="pending", index=True) # pending, recording, ingesting, analyzing, ready, error
    duration_sec: float = Field(default=0.0)
    audio_path: Optional[str] = Field(default=None)
    video_path: Optional[str] = Field(default=None)
    chat_path: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Transcript(SQLModel, table=True):
    __tablename__ = "transcripts"

    id: str = Field(default_factory=gen_uuid, primary_key=True)
    project_id: str = Field(index=True)
    full_text: str = Field(sa_column=Column(Text))
    segments_json: list = Field(default=[], sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)


class Moment(SQLModel, table=True):
    __tablename__ = "moments"

    id: str = Field(default_factory=gen_uuid, primary_key=True)
    project_id: str = Field(index=True)
    start_sec: float = Field(default=0.0)
    end_sec: float = Field(default=0.0)
    duration_sec: float = Field(default=0.0)
    hook: str = Field(default="")
    title: str = Field(default="")
    reason: str = Field(default="")
    virality_score: int = Field(default=70, index=True) # 0-100
    event_comment: Optional[str] = Field(default=None)
    tags_json: list = Field(default=[], sa_column=Column(JSON))
    selected: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now)


class Clip(SQLModel, table=True):
    __tablename__ = "clips"

    id: str = Field(default_factory=gen_uuid, primary_key=True)
    project_id: str = Field(index=True)
    moment_id: Optional[str] = Field(default=None, index=True)
    title: str = Field(default="Nuevo Clip")
    hook_text: str = Field(default="")
    event_comment: Optional[str] = Field(default=None)
    layout: str = Field(default="auto") # auto, duo_split, speaker_focus, split_screen, centered_face, blur_bg, gaming_zoom
    content_mode: str = Field(default="auto") # auto, gaming_gta, podcast, reaction
    hook_persistence: str = Field(default="intro") # intro (0-4.5s), always (todo el clip), off
    show_subtitles: bool = Field(default=True)
    video_transitions: bool = Field(default=True)
    subtitle_style: str = Field(default="hormozi") # hormozi, karaoke, neon, minimal, mrbeast
    aspect_ratio: str = Field(default="9:16")
    start_sec: float = Field(default=0.0)
    end_sec: float = Field(default=0.0)
    duration_sec: float = Field(default=0.0)
    render_engine: str = Field(default="ffmpeg") # ffmpeg, hyperframes
    status: str = Field(default="draft", index=True) # draft, rendering, ready, failed
    output_path: Optional[str] = Field(default=None)
    thumbnail_path: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class StudioVideo(SQLModel, table=True):
    __tablename__ = "studio_videos"

    id: str = Field(default_factory=gen_uuid, primary_key=True)
    title: str = Field(default="Video Motion Graphics")
    topic: str = Field(default="")
    style: str = Field(default="curiosities") # curiosities, top5, history, data_charts, reddit
    voice_name: str = Field(default="es-MX-DaliaNeural")
    script_json: dict = Field(default={}, sa_column=Column(JSON))
    scene_plan_json: list = Field(default=[], sa_column=Column(JSON))
    status: str = Field(default="draft", index=True) # draft, voice_ready, rendered, failed
    audio_path: Optional[str] = Field(default=None)
    output_path: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: str = Field(default_factory=gen_uuid, primary_key=True)
    job_type: str = Field(index=True) # ingest, analyze, render_clip, studio_render, publish
    target_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="queued", index=True) # queued, running, completed, failed
    progress: int = Field(default=0) # 0 to 100
    message: str = Field(default="Iniciando tarea...")
    result_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    error_message: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SocialAccount(SQLModel, table=True):
    __tablename__ = "social_accounts"

    id: str = Field(default_factory=gen_uuid, primary_key=True)
    platform: str = Field(index=True) # instagram, facebook, tiktok, youtube
    account_name: str = Field(default="")
    account_id: str = Field(default="")
    access_token_enc: str = Field(default="")
    refresh_token_enc: Optional[str] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None)
    status: str = Field(default="active") # active, expired
    created_at: datetime = Field(default_factory=utc_now)


class Post(SQLModel, table=True):
    __tablename__ = "posts"

    id: str = Field(default_factory=gen_uuid, primary_key=True)
    media_type: str = Field(default="clip") # clip, studio_video
    media_id: str = Field(index=True)
    caption_base: str = Field(default="")
    platforms_json: list = Field(default=[], sa_column=Column(JSON))
    scheduled_for: Optional[datetime] = Field(default=None, index=True)
    status: str = Field(default="draft", index=True) # draft, scheduled, published, failed
    created_at: datetime = Field(default_factory=utc_now)


class PostTarget(SQLModel, table=True):
    __tablename__ = "post_targets"

    id: str = Field(default_factory=gen_uuid, primary_key=True)
    post_id: str = Field(index=True)
    platform: str = Field(index=True)
    remote_post_id: Optional[str] = Field(default=None)
    status: str = Field(default="pending", index=True) # pending, publishing, published, draft_inbox, failed
    error_message: Optional[str] = Field(default=None)
    published_at: Optional[datetime] = Field(default=None)


class PostMetric(SQLModel, table=True):
    __tablename__ = "post_metrics"

    id: str = Field(default_factory=gen_uuid, primary_key=True)
    post_target_id: str = Field(index=True)
    platform: str = Field(index=True)
    views: int = Field(default=0)
    likes: int = Field(default=0)
    comments: int = Field(default=0)
    shares: int = Field(default=0)
    watch_time_sec: float = Field(default=0.0)
    recorded_at: datetime = Field(default_factory=utc_now, index=True)


class PulpoUsage(SQLModel, table=True):
    __tablename__ = "pulpo_usage"

    id: str = Field(default_factory=gen_uuid, primary_key=True)
    key_prefix: str = Field(index=True)
    model: str = Field(index=True)
    task: str = Field(index=True)
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    status_code: int = Field(default=200)
    latency_ms: int = Field(default=0)
    timestamp: datetime = Field(default_factory=utc_now, index=True)


class AppSetting(SQLModel, table=True):
    __tablename__ = "app_settings"

    key: str = Field(primary_key=True)
    value: str = Field(default="")
    updated_at: datetime = Field(default_factory=utc_now)
