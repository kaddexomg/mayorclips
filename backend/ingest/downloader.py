import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
import httpx
import yt_dlp
from app.config import MEDIA_DIR, CACHE_DIR, FFMPEG_PATH


class VideoIngester:
    """Zero-Bloat Stream & Video Ingester: Handles short clips AND 8-10 hour VODs without downloading gigabytes."""

    def __init__(self):
        self.ffmpeg_location = str(Path(FFMPEG_PATH).parent)

    def extract_info(self, url: str) -> Dict[str, Any]:
        """Extracts stream/video metadata, heatmap, and direct HLS/HTTP stream URLs without downloading."""
        opts = {
            "quiet": True,
            "skip_download": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        duration = float(info.get("duration") or 0.0)
        title = info.get("title") or "Stream Sin Título"
        uploader = info.get("uploader") or info.get("channel") or "Streamer"
        thumbnail = info.get("thumbnail")
        extractor = (info.get("extractor_key") or "generic").lower()
        formats = info.get("formats") or []

        # Pick lowest bandwidth stream containing audio for fast 0-bloat analysis (e.g. Kick 160p or ba)
        low_stream_url = None
        audio_only = [f for f in formats if f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none") and f.get("url")]
        if audio_only:
            audio_only.sort(key=lambda f: f.get("tbr") or 9999)
            low_stream_url = audio_only[0]["url"]
        else:
            muxed_with_audio = [f for f in formats if f.get("acodec") not in (None, "none") and f.get("url")]
            if muxed_with_audio:
                muxed_with_audio.sort(key=lambda f: f.get("tbr") or 9999)
                low_stream_url = muxed_with_audio[0]["url"]

        # Pick best <=1080p muxed HLS/MP4 stream if available (ideal for Kick/Twitch direct FFmpeg slice)
        hq_muxed_url = None
        muxed_hq = [
            f for f in formats
            if f.get("acodec") not in (None, "none")
            and f.get("vcodec") not in (None, "none")
            and (f.get("height") or 0) <= 1080
            and f.get("url")
        ]
        if muxed_hq:
            muxed_hq.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0), reverse=True)
            hq_muxed_url = muxed_hq[0]["url"]

        # Check YouTube auto-captions / subtitles in Spanish or English
        subs_url = None
        for src_dict in [info.get("subtitles") or {}, info.get("automatic_captions") or {}]:
            for lang in ["es", "es-419", "es-ES", "en"]:
                if lang in src_dict:
                    entries = src_dict[lang]
                    json3 = [e for e in entries if e.get("ext") == "json3"]
                    if json3:
                        subs_url = json3[0]["url"]
                        break
            if subs_url:
                break

        return {
            "id": info.get("id"),
            "title": title,
            "duration_sec": duration,
            "streamer": uploader,
            "channel_id": info.get("channel_id"),
            "timestamp": info.get("timestamp"),
            "thumbnail": thumbnail,
            "platform": extractor,
            "heatmap": info.get("heatmap") or [],
            "chapters": info.get("chapters") or [],
            "low_stream_url": low_stream_url,
            "hq_muxed_url": hq_muxed_url,
            "subs_url": subs_url,
            "url": url,
        }

    def fetch_youtube_transcript_segments(self, subs_url: str) -> List[Dict[str, Any]]:
        """Downloads and parses YouTube JSON3 auto-captions (<500KB) in <1s without downloading any audio."""
        if not subs_url:
            return []
        try:
            r = httpx.get(subs_url, timeout=15.0)
            if r.status_code != 200:
                return []
            events = r.json().get("events", [])
            segments = []
            for ev in events:
                segs = ev.get("segs")
                if not segs:
                    continue
                txt = "".join(s.get("utf8", "") for s in segs).strip().replace("\n", " ")
                if txt:
                    start_sec = round(ev.get("tStartMs", 0) / 1000.0, 2)
                    dur_sec = round(ev.get("dDurationMs", 2000) / 1000.0, 2)
                    segments.append({"start": start_sec, "end": start_sec + dur_sec, "text": txt})
            return segments
        except Exception as e:
            print(f"[INGEST] Warning reading YouTube captions: {e}")
            return []

    def extract_audio_slice(
        self,
        stream_url: str,
        start_sec: float,
        duration_sec: float,
        output_path: str,
        fallback_page_url: Optional[str] = None,
    ) -> str:
        """Extracts a surgical audio slice (e.g. 90s -> ~550KB) directly from HLS/HTTP without downloading the VOD."""
        if stream_url:
            cmd = [
                FFMPEG_PATH,
                "-y",
                "-hide_banner",
                "-loglevel", "error",
                "-ss", str(round(max(0.0, start_sec), 2)),
                "-t", str(round(duration_sec, 2)),
                "-i", stream_url,
                "-vn",
                "-c:a", "aac",
                "-b:a", "48k",
                output_path,
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            if proc.returncode == 0 and Path(output_path).exists() and Path(output_path).stat().st_size > 1000:
                return output_path

        # Fallback to yt-dlp section download if direct stream seek failed
        if fallback_page_url:
            end_sec = start_sec + duration_sec
            opts = {
                "format": "ba/worst",
                "outtmpl": output_path,
                "ffmpeg_location": self.ffmpeg_location,
                "download_ranges": yt_dlp.utils.download_range_func(None, [(max(0.0, start_sec), end_sec)]),
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a", "preferredquality": "64"}],
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([fallback_page_url])
            if Path(output_path).exists():
                return output_path
            matches = list(Path(output_path).parent.glob(f"{Path(output_path).stem}.*"))
            if matches:
                return str(matches[0])

        raise RuntimeError(f"No se pudo extraer el fragmento de audio en {start_sec}s.")

    def download_audio_first(self, url: str, project_id: str, progress_hook=None) -> str:
        """Downloads audio ONLY for short videos (<15 min) safely capped at lowest bitrate."""
        out_template = str(MEDIA_DIR / f"{project_id}_audio.%(ext)s")
        opts = {
            "format": "ba/worst",
            "outtmpl": out_template,
            "ffmpeg_location": self.ffmpeg_location,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "96",
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
            matches = list(MEDIA_DIR.glob(f"{project_id}_audio.*"))
            if matches:
                return str(matches[0])
            raise FileNotFoundError(f"No se pudo descargar el audio para el proyecto {project_id}")
        return str(final_path)

    def download_clip_section(
        self,
        url: str,
        start_sec: float,
        end_sec: float,
        output_filename: str,
        hq_muxed_url: Optional[str] = None,
    ) -> str:
        """Downloads ONLY the exact approved 1080p clip slice (e.g. 45s) in ~4-10s without touching the full 22GB VOD."""
        buffer_before = max(0.0, start_sec - 0.5)
        dur = max(3.0, (end_sec + 0.5) - buffer_before)
        target = MEDIA_DIR / output_filename

        # Fast path: Direct FFmpeg HLS/MP4 seek (works in ~4.5s on Kick & Twitch 1080p60!)
        if hq_muxed_url and (".m3u8" in hq_muxed_url or "cloudfront" in hq_muxed_url or "ttvnw" in hq_muxed_url):
            cmd = [
                FFMPEG_PATH,
                "-y",
                "-hide_banner",
                "-loglevel", "error",
                "-ss", str(round(buffer_before, 2)),
                "-t", str(round(dur, 2)),
                "-i", hq_muxed_url,
                "-c", "copy",
                str(target),
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
            if proc.returncode == 0 and target.exists() and target.stat().st_size > 10000:
                return str(target)

        # Standard path: yt-dlp download_ranges (handles YouTube split 1080p video+audio seamlessly)
        out_template = str(MEDIA_DIR / f"{Path(output_filename).stem}.%(ext)s")
        opts = {
            "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/best",
            "outtmpl": out_template,
            "ffmpeg_location": self.ffmpeg_location,
            "download_ranges": yt_dlp.utils.download_range_func(None, [(buffer_before, buffer_before + dur)]),
            "force_keyframes_at_cuts": True,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        if target.exists():
            return str(target)
        matches = list(MEDIA_DIR.glob(f"{Path(output_filename).stem}.*"))
        if matches:
            return str(matches[0])
        raise FileNotFoundError(f"Error descargando sección {buffer_before}-{buffer_before + dur} para {url}")


ingester = VideoIngester()
