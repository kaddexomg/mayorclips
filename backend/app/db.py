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
    from app.models import (
        Project, Transcript, Moment, Clip, StudioVideo,
        Job, SocialAccount, Post, PostTarget, PostMetric, PulpoUsage
    )
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
