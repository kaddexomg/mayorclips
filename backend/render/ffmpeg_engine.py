import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import FFMPEG_PATH, RENDERS_DIR

def get_best_h264_encoder() -> tuple[str, list[str]]:
    """Returns hardware AMD AMF encoder args if available, else libx264 veryfast."""
    try:
        res = subprocess.run([FFMPEG_PATH, "-hide_banner", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if "h264_amf" in res.stdout:
            return "h264_amf", ["-c:v", "h264_amf", "-quality", "speed"]
    except Exception:
        pass
    return "libx264", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22"]

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

    # Layout filters
    # Target resolution: 1080x1920
    if layout == "split_screen":
        # Top 35% webcam (1080x672), Bottom 65% gameplay (1080x1248)
        filter_complex = (
            f"[0:v]split=2[cam][game];"
            f"[cam]crop=in_w*0.35:in_h*0.35:in_w*0.02:in_h*0.05,scale=1080:672:force_original_aspect_ratio=increase,crop=1080:672[top];"
            f"[game]scale=1080:1248:force_original_aspect_ratio=increase,crop=1080:1248[bot];"
            f"[top][bot]vstack=inputs=2[outv]{sub_filter}"
        )
    elif layout == "blur_bg":
        # 16:9 centered on 9:16 blurred background
        filter_complex = (
            f"[0:v]split=2[fg][bg];"
            f"[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg_blur];"
            f"[fg]scale=1080:608:force_original_aspect_ratio=decrease[fg_sharp];"
            f"[bg_blur][fg_sharp]overlay=(W-w)/2:(H-h)/2[outv]{sub_filter}"
        )
    else: # centered_face / default crop to 9:16
        filter_complex = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[outv]{sub_filter}"
        )

    cmd = [
        FFMPEG_PATH,
        "-y",
        *seek_args,
        "-i", str(source_video_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        *encoder_args,
        "-c:a", "aac",
        "-b:a", "160k",
        "-movflags", "+faststart",
        str(output_path)
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    except subprocess.CalledProcessError as e:
        # If AMF failed, retry once with libx264
        if "amf" in encoder_name:
            cmd_fallback = [
                FFMPEG_PATH, "-y", *seek_args, "-i", str(source_video_path),
                "-filter_complex", filter_complex, "-map", "[outv]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
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
