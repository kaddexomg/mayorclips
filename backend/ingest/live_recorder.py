import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import MEDIA_DIR, FFMPEG_PATH
from ingest.downloader import ingester


class LiveRecorderManager:
    """Manages active FFmpeg MPEG-TS capture processes for ongoing Twitch, Kick, and YouTube Live streams."""

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _probe_duration(self, ts_path: str) -> float:
        try:
            ffprobe = str(Path(FFMPEG_PATH).parent / "ffprobe.exe")
            if not Path(ffprobe).exists():
                ffprobe = "ffprobe"
            out = subprocess.check_output(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", ts_path],
                text=True,
                timeout=10,
            )
            return round(float(out.strip()), 2)
        except Exception:
            return 0.0

    def start_capture(self, project_id: str, url: str, max_duration_sec: int = 900) -> Dict[str, Any]:
        info = ingester.extract_info(url)
        hq_muxed = info.get("hq_muxed_url")
        hq_video = info.get("hq_video_url")
        best_audio = info.get("best_audio_url") or info.get("low_stream_url")

        out_ts = str(MEDIA_DIR / f"live_{project_id[:8]}.ts")
        if Path(out_ts).exists():
            try:
                Path(out_ts).unlink()
            except Exception:
                pass

        cap_sec = max(45, min(1800, int(max_duration_sec)))
        cmd = [FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "warning"]
        if hq_muxed:
            cmd.extend(["-i", hq_muxed, "-t", str(cap_sec), "-c", "copy", "-f", "mpegts", out_ts])
        elif hq_video and best_audio:
            cmd.extend(["-i", hq_video, "-i", best_audio, "-map", "0:v:0", "-map", "1:a:0", "-t", str(cap_sec), "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-f", "mpegts", out_ts])
        elif hq_video or best_audio:
            src = hq_video or best_audio
            cmd.extend(["-i", src, "-t", str(cap_sec), "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-f", "mpegts", out_ts])
        else:
            raise RuntimeError("No se encontró un flujo de transmisión en vivo legible para este enlace.")

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Give FFmpeg 2s to verify live HLS connection didn't immediately fail
        time.sleep(2.0)
        if proc.poll() is not None:
            err = (proc.stderr.read() or b"").decode("utf-8", errors="ignore")
            raise RuntimeError(f"FFmpeg no pudo abrir el directo en vivo: {err[:300]}")

        self._sessions[project_id] = {
            "proc": proc,
            "output_path": out_ts,
            "started_at": time.time(),
            "max_duration_sec": cap_sec,
            "title": info.get("title") or "Directo en Vivo",
            "streamer": info.get("streamer") or "Streamer",
            "platform": info.get("platform") or "live",
            "is_live": info.get("is_live", True),
        }
        return self.get_status(project_id)

    def get_status(self, project_id: str) -> Dict[str, Any]:
        sess = self._sessions.get(project_id)
        if not sess:
            return {"active": False, "recording": False, "elapsed_sec": 0.0, "file_size_mb": 0.0}

        proc: subprocess.Popen = sess["proc"]
        alive = proc.poll() is None
        out_path = Path(sess["output_path"])
        size_mb = round(out_path.stat().st_size / (1024 * 1024), 2) if out_path.exists() else 0.0
        elapsed = round(time.time() - sess["started_at"], 1)
        return {
            "active": True,
            "recording": alive,
            "elapsed_sec": elapsed,
            "max_duration_sec": sess["max_duration_sec"],
            "file_size_mb": size_mb,
            "output_path": sess["output_path"],
            "title": sess["title"],
            "streamer": sess["streamer"],
            "is_live": sess["is_live"],
        }

    def stop_capture(self, project_id: str) -> Dict[str, Any]:
        sess = self._sessions.get(project_id)
        if not sess:
            return {"stopped": True, "duration_sec": 0.0, "output_path": None}

        proc: subprocess.Popen = sess["proc"]
        if proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.write(b"q\n")
                    proc.stdin.flush()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.terminate()
                    proc.wait(timeout=4)
                except Exception:
                    proc.kill()

        out_path = sess["output_path"]
        dur = self._probe_duration(out_path) if Path(out_path).exists() else 0.0
        if dur <= 0.0:
            dur = round(max(1.0, time.time() - sess["started_at"]), 1)

        self._sessions.pop(project_id, None)
        return {
            "stopped": True,
            "output_path": out_path,
            "duration_sec": dur,
            "title": sess.get("title"),
            "streamer": sess.get("streamer"),
        }


live_recorder = LiveRecorderManager()
