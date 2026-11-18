import os
import re
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
import yt_dlp
from app.config import MEDIA_DIR, CACHE_DIR, FFMPEG_PATH

class VideoIngester:
    """Audio-first ingester for Twitch, Kick, and YouTube."""

    def __init__(self):
        self.ffmpeg_location = str(Path(FFMPEG_PATH).parent)

    def extract_info(self, url: str) -> Dict[str, Any]:
        """Extracts stream/video metadata without downloading."""
        opts = {
            "quiet": True,
            "skip_download": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get("duration", 0)
            title = info.get("title", "Video Sin Título")
            uploader = info.get("uploader", info.get("channel", "Streamer"))
            thumbnail = info.get("thumbnail", None)
            extractor = info.get("extractor_key", "generic").lower()
            return {
                "title": title,
                "duration_sec": duration,
                "streamer": uploader,
                "thumbnail": thumbnail,
                "platform": extractor,
                "url": url
            }

    def download_audio_first(self, url: str, project_id: str, progress_hook=None) -> str:
        """Downloads ONLY the audio stream (~50-100MB) to conserve bandwidth, disk, and RAM."""
        out_template = str(MEDIA_DIR / f"{project_id}_audio.%(ext)s")
        
        opts = {
            "format": "ba/b",
            "outtmpl": out_template,
            "ffmpeg_location": self.ffmpeg_location,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "128",
            }],
            "quiet": True,
            "no_warnings": True,
        }
        if progress_hook:
            opts["progress_hooks"] = [progress_hook]

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        final_path = MEDIA_DIR / f"{project_id}_audio.m4a"
        if not final_path.exists():
            # Check for any audio file with that prefix
            matches = list(MEDIA_DIR.glob(f"{project_id}_audio.*"))
            if matches:
                return str(matches[0])
            raise FileNotFoundError(f"No se pudo descargar el audio para el proyecto {project_id}")
        return str(final_path)

    def download_clip_section(self, url: str, start_sec: float, end_sec: float, output_filename: str) -> str:
        """Downloads ONLY the specific selected video slice (e.g. 45s) using yt-dlp section download."""
        buffer_before = max(0.0, start_sec - 1.5)
        buffer_after = end_sec + 1.5
        section_str = f"*{buffer_before}-{buffer_after}"
        
        out_template = str(MEDIA_DIR / output_filename)
        opts = {
            "format": "bv*[height<=1080]+ba/b[height<=1080]/best",
            "outtmpl": out_template,
            "ffmpeg_location": self.ffmpeg_location,
            "download_ranges": yt_dlp.utils.download_range_func(None, [(buffer_before, buffer_after)]),
            "force_keyframes_at_cuts": True,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        target = Path(out_template)
        if target.exists():
            return str(target)
        # Check potential auto extension
        matches = list(MEDIA_DIR.glob(f"{Path(output_filename).stem}.*"))
        if matches:
            return str(matches[0])
        raise FileNotFoundError(f"Error descargando sección {section_str} para {url}")

ingester = VideoIngester()
