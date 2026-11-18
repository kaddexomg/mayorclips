import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = BASE_DIR / "backend"
STORAGE_DIR = BASE_DIR / "storage"
MEDIA_DIR = STORAGE_DIR / "media"
RENDERS_DIR = STORAGE_DIR / "renders"
CACHE_DIR = STORAGE_DIR / "cache"
TEMPLATES_DIR = BASE_DIR / "hf-templates"

# Ensure directories exist
for d in [STORAGE_DIR, MEDIA_DIR, RENDERS_DIR, CACHE_DIR, TEMPLATES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Load .env
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

# Gemini Keys pool
def get_gemini_keys() -> list[str]:
    raw = os.getenv("GEMINI_API_KEYS", "[]")
    try:
        keys = json.loads(raw)
        if isinstance(keys, list):
            return [k.strip() for k in keys if k.strip()]
    except Exception:
        pass
    return []

GEMINI_API_KEYS = get_gemini_keys()

# Ports & URLs
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.getenv("FRONTEND_PORT", "5173"))
LOCAL_SQLITE_URL = os.getenv("LOCAL_SQLITE_URL", f"sqlite:///{BASE_DIR / 'mayorclips.db'}")

# VPS & Database
VPS_HOST = os.getenv("VPS_HOST", "166.0.112.247")
VPS_PORT = int(os.getenv("VPS_PORT", "8010"))
VPS_API_TOKEN = os.getenv("VPS_API_TOKEN", "mc_sec_019a8f4c82de92b0e6e7c10b784f18d5")

# Secrets
FERNET_SECRET_KEY = os.getenv("FERNET_SECRET_KEY", "z78Gv8b9qL6YFjA2g-9V3rE4K1o7M4u2xP0wQ8sT5lA=")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")

# FFmpeg detection
def find_ffmpeg() -> str:
    from shutil import which
    found = which("ffmpeg")
    if found:
        return found
    standard = Path(r"C:\Users\PC\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe")
    if standard.exists():
        return str(standard)
    return "ffmpeg"

FFMPEG_PATH = find_ffmpeg()
