import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import FFMPEG_PATH, RENDERS_DIR

def get_best_h264_encoder() -> tuple[str, list[str]]:
    """Returns hardware AMD AMF encoder args with balanced 3.5Mbps mobile bitrate if available, else libx264."""
    try:
        res = subprocess.run([FFMPEG_PATH, "-hide_banner", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if "h264_amf" in res.stdout:
            return "h264_amf", ["-c:v", "h264_amf", "-quality", "speed", "-b:v", "3500k", "-maxrate", "5000k", "-bufsize", "7000k"]
    except Exception:
        pass
    return "libx264", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]

def extract_frame_jpeg(video_path: str, out_jpg: str, at_sec: float = 2.0) -> Optional[str]:
    """Extracts a single JPEG frame for Gemini Vision webcam/layout detection."""
    cmd = [
        FFMPEG_PATH, "-y", "-hide_banner", "-loglevel", "error",
        "-ss", str(round(at_sec, 2)), "-i", str(video_path),
        "-vframes", "1", "-q:v", "4", str(out_jpg)
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    if proc.returncode == 0 and Path(out_jpg).exists():
        return str(out_jpg)
    return None

def render_vertical_clip(
    source_video_path: str,
    output_filename: str,
    layout: str = "split_screen",
    start_sec: float = 0.0,
    end_sec: float = 0.0,
    ass_subtitle_path: Optional[str] = None,
    webcam_box: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """Renders 1080x1920 vertical video with specified layout, hardware encoding, and burned-in subtitles."""
    output_path = RENDERS_DIR / output_filename
    thumb_path = RENDERS_DIR / f"{Path(output_filename).stem}_thumb.jpg"
    encoder_name, encoder_args = get_best_h264_encoder()

    # Time limits
    seek_args = []
    if start_sec > 0:
        seek_args.extend(["-ss", str(round(start_sec, 2))])
    if end_sec > start_sec:
        seek_args.extend(["-t", str(round(end_sec - start_sec, 2))])

    # Windows FFmpeg subtitle path escaping
    sub_filter = ""
    if ass_subtitle_path and Path(ass_subtitle_path).exists():
        escaped_sub = str(Path(ass_subtitle_path).resolve()).replace("\\", "/").replace(":", "\\:")
        sub_filter = f",subtitles='{escaped_sub}'"

    # Clamp normalized webcam box safely within [0..1]
    wb = webcam_box or {"x": 0.02, "y": 0.04, "w": 0.30, "h": 0.35}
    wx = max(0.0, min(0.85, float(wb.get("x", 0.02))))
    wy = max(0.0, min(0.85, float(wb.get("y", 0.04))))
    ww = max(0.12, min(1.0 - wx, float(wb.get("w", 0.30))))
    wh = max(0.12, min(1.0 - wy, float(wb.get("h", 0.35))))

    # Layout filters -> Target resolution: 1080x1920, square pixels (setsar=1), subtitles applied BEFORE [outv]
    if layout == "split_screen":
        filter_complex = (
            f"[0:v]split=2[cam][game];"
            f"[cam]crop=in_w*{ww:.3f}:in_h*{wh:.3f}:in_w*{wx:.3f}:in_h*{wy:.3f},scale=1080:672:force_original_aspect_ratio=increase,crop=1080:672,setsar=1[top];"
            f"[game]scale=1080:1248:force_original_aspect_ratio=increase,crop=1080:1248,setsar=1[bot];"
            f"[top][bot]vstack=inputs=2{sub_filter}[outv]"
        )
    elif layout == "blur_bg":
        # Downscale first -> fast blur -> upscale: 16x faster on CPU with identical look
        filter_complex = (
            f"[0:v]split=2[fg][bg];"
            f"[bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=8:2,scale=1080:1920,setsar=1[bg_blur];"
            f"[fg]scale=1080:608:force_original_aspect_ratio=decrease,setsar=1[fg_sharp];"
            f"[bg_blur][fg_sharp]overlay=(W-w)/2:(H-h)/2{sub_filter}[outv]"
        )
    else: # centered_face / podcast / default crop to 9:16
        filter_complex = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1{sub_filter}[outv]"
        )

    cmd = [
        FFMPEG_PATH,
        "-y",
        *seek_args,
        "-i", str(source_video_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-r", "30",
        *encoder_args,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-movflags", "+faststart",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    except subprocess.CalledProcessError:
        if "amf" in encoder_name:
            cmd_fallback = [
                FFMPEG_PATH, "-y", *seek_args, "-i", str(source_video_path),
                "-filter_complex", filter_complex, "-map", "[outv]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(output_path)
            ]
            subprocess.run(cmd_fallback, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        else:
            raise

    # Generate thumbnail snapshot at 1.5s
    thumb_cmd = [
        FFMPEG_PATH, "-y", "-ss", "00:00:01.50", "-i", str(output_path),
        "-vframes", "1", "-vf", "scale=360:640", str(thumb_path)
    ]
    try:
        subprocess.run(thumb_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    except Exception:
        pass

    return {
        "output_path": str(output_path),
        "thumbnail_path": str(thumb_path) if thumb_path.exists() else None,
        "encoder_used": encoder_name
    }
