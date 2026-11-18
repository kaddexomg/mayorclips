from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy import event
from app.config import LOCAL_SQLITE_URL

engine = create_engine(
    LOCAL_SQLITE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

# Enable WAL (Write-Ahead Logging) mode and foreign keys for high-performance concurrent SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

def init_db():
    from sqlalchemy import text
    from app.models import (
        Project, Transcript, Moment, Clip, StudioVideo,
        Job, SocialAccount, Post, PostTarget, PostMetric, PulpoUsage, AppSetting
    )
    SQLModel.metadata.create_all(engine)

    # Safe SQLite migration for new Project & Clip control columns
    migrations = [
        ("projects", "context_hint", "TEXT"),
        ("clips", "content_mode", "TEXT DEFAULT 'auto'"),
        ("clips", "hook_persistence", "TEXT DEFAULT 'intro'"),
        ("clips", "show_subtitles", "BOOLEAN DEFAULT 1"),
        ("clips", "video_transitions", "BOOLEAN DEFAULT 1"),
    ]
    with engine.begin() as conn:
        for table, col, col_type in migrations:
            try:
                cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]
                if col not in cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
            except Exception as e:
                print(f"[DB MIGRATION] Skipped {table}.{col}: {e}")

        # Clean up zombie jobs left in running/queued state after an unexpected server restart
        try:
            conn.execute(
                text(
                    "UPDATE jobs SET status='failed', message='Interrumpido por reinicio del servidor', "
                    "error_message='El servidor se reinició mientras este trabajo estaba en ejecución.' "
                    "WHERE status IN ('running', 'queued')"
                )
            )
            conn.execute(
                text(
                    "UPDATE projects SET status='error', error_message='Captura o análisis interrumpido por reinicio.' "
                    "WHERE status IN ('recording', 'analyzing')"
                )
            )
        except Exception:
            pass

def get_session():
    with Session(engine) as session:
        yield session
