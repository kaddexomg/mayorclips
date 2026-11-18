import os
import uuid
import httpx
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import MEDIA_DIR, FFMPEG_PATH
from higgsfield.models import VideoGenerationRequest, CameraMotionType

class HiggsfieldConnector:
    """Hybrid Cinematic Video Engine: Compatible with official Higgsfield MCP / API + Free Open Cloud Fallback."""

    def __init__(self):
        self.api_key = os.getenv("HIGGSFIELD_API_KEY", "").strip()

    @property
    def has_subscription(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 8)

    async def generate_cinematic_broll(self, req: VideoGenerationRequest) -> Dict[str, Any]:
        """Generates video with camera control. Uses official Higgsfield if key configured, else Open Cloud + Camera Motion."""
        if self.has_subscription:
            return await self._call_official_higgsfield(req)
        else:
            return await self._call_open_alternative(req)

    async def _call_official_higgsfield(self, req: VideoGenerationRequest) -> Dict[str, Any]:
        """Official Higgsfield API integration compatible with higgsfield-mcp-unified."""
        url = "https://api.higgsfield.ai/v1/video/generations"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": req.prompt,
            "camera": {
                "motion": req.camera.motion.value,
                "speed": req.camera.speed,
                "strength": req.camera.strength
            },
            "aspect_ratio": req.aspect_ratio,
            "duration": req.duration_sec,
            "model": req.higgsfield_model
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            res = await client.post(url, headers=headers, json=payload)
            if res.status_code not in (200, 201):
                raise RuntimeError(f"Error en Higgsfield API: {res.text}")
            data = res.json()
            return {
                "engine": "higgsfield-official",
                "video_url": data.get("video_url") or data.get("url"),
                "motion_applied": req.camera.motion.value
            }

    async def _call_open_alternative(self, req: VideoGenerationRequest) -> Dict[str, Any]:
        """Open-source cloud fallback with cinematic camera motion applied via FFmpeg zoompan/orbit."""
        import urllib.parse
        safe_prompt = urllib.parse.quote(req.prompt)
        w, h = (1080, 1920) if req.aspect_ratio == "9:16" else (1920, 1080)

        # 1. Fetch high-res conceptual visual via free cloud generator
        img_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width={w}&height={h}&nologo=true"
        temp_img = MEDIA_DIR / f"cinematic_base_{uuid.uuid4().hex[:8]}.jpg"
        out_mp4 = MEDIA_DIR / f"broll_{uuid.uuid4().hex[:8]}.mp4"

        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.get(img_url)
            if r.status_code == 200:
                with open(temp_img, "wb") as f:
                    f.write(r.content)
            else:
                raise RuntimeError("No se pudo obtener imagen base para el B-roll cinematográfico.")

        # 2. Apply cinematic camera trajectory via FFmpeg zoompan filter
        fps = 30
        total_frames = int(req.duration_sec * fps)
        
        # Motion math
        motion = req.camera.motion
        if motion == CameraMotionType.ZOOM_IN:
            # Zoom in smoothly from 1.0 to 1.3 centered
            vf = f"zoompan=z='min(zoom+0.0015,1.35)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s={w}x{h}:fps={fps}"
        elif motion == CameraMotionType.ZOOM_OUT:
            # Zoom out from 1.35 to 1.0
            vf = f"zoompan=z='if(lte(zoom,1.0),1.35,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s={w}x{h}:fps={fps}"
        elif motion == CameraMotionType.PAN_RIGHT:
            # Pan from left to right with mild zoom
            vf = f"zoompan=z='1.2':x='if(lte(on,1),(iw-iw/zoom)/2,x+2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s={w}x{h}:fps={fps}"
        elif motion == CameraMotionType.PAN_LEFT:
            # Pan from right to left
            vf = f"zoompan=z='1.2':x='if(lte(on,1),iw/zoom,x-2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s={w}x{h}:fps={fps}"
        else: # ORBIT_3D / TILT
            vf = f"zoompan=z='1.15+0.05*sin(2*PI*on/{total_frames})':x='iw/2-(iw/zoom/2)+15*cos(2*PI*on/{total_frames})':y='ih/2-(ih/zoom/2)+15*sin(2*PI*on/{total_frames})':d={total_frames}:s={w}x{h}:fps={fps}"

        cmd = [
            FFMPEG_PATH, "-y",
            "-loop", "1",
            "-i", str(temp_img),
            "-vf", vf,
            "-t", str(req.duration_sec),
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            str(out_mp4)
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if proc.returncode != 0:
            raise RuntimeError(f"Error generando B-roll cinematográfico: {proc.stderr.decode('utf-8', errors='ignore')}")

        return {
            "engine": "open-camera-trajectory",
            "video_path": str(out_mp4),
            "video_url": f"/media/{out_mp4.name}",
            "motion_applied": motion.value,
            "duration_sec": req.duration_sec
        }

higgsfield_connector = HiggsfieldConnector()
