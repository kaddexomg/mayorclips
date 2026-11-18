from pathlib import Path
from typing import List, Dict, Any, Optional
import cv2
import numpy as np

from app.config import BACKEND_DIR

YUNET_MODEL_PATH = BACKEND_DIR / "assets" / "models" / "face_detection_yunet_2023mar.onnx"


def analyze_speakers_and_motion(video_path: str, sample_fps: float = 3.0) -> Dict[str, Any]:
    """Tracks faces and identifies active speakers via YuNet + mouth-region motion energy in ~2-3s on CPU."""
    if not YUNET_MODEL_PATH.exists() or not Path(video_path).exists():
        return {"speakers": [], "timeline_segments": [], "recommended_layout": "blur_bg"}

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return {"speakers": [], "timeline_segments": [], "recommended_layout": "blur_bg"}

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration_sec = total_frames / native_fps if native_fps > 0 else 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)

    # Downscale to 480px width for fast CPU detection
    target_w = 480
    target_h = max(160, int(src_h * (target_w / max(1, src_w))))
    det = cv2.FaceDetectorYN.create(str(YUNET_MODEL_PATH), "", (target_w, target_h), 0.55, 0.3, 12)

    step_frames = max(1, int(round(native_fps / sample_fps)))
    clusters: List[Dict[str, Any]] = [] # Persistent face clusters {cx, cy, w, h, hits, motion_sum}
    frame_events: List[Dict[str, Any]] = []

    prev_gray = None
    frame_idx = 0

    while cap.grab():
        if frame_idx % step_frames == 0:
            ret, frame = cap.retrieve()
            if not ret:
                break
            t_sec = frame_idx / native_fps
            small = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            _, faces = det.detect(small)
            detected_boxes = []
            if faces is not None:
                for f in faces:
                    fx, fy, fw, fh = [float(v) for v in f[:4]]
                    if fw < 10 or fh < 10:
                        continue
                    nx, ny = fx / target_w, fy / target_h
                    nw, nh = fw / target_w, fh / target_h
                    cx, cy = nx + nw / 2.0, ny + nh / 2.0

                    # Compute mouth/jaw motion energy (lower 45% of face box)
                    motion_val = 0.0
                    if prev_gray is not None:
                        my0 = max(0, min(target_h - 1, int(fy + fh * 0.52)))
                        my1 = max(my0 + 1, min(target_h, int(fy + fh * 0.98)))
                        mx0 = max(0, min(target_w - 1, int(fx + fw * 0.15)))
                        mx1 = max(mx0 + 1, min(target_w, int(fx + fw * 0.85)))
                        diff = cv2.absdiff(gray[my0:my1, mx0:mx1], prev_gray[my0:my1, mx0:mx1])
                        motion_val = float(np.mean(diff))

                    # Match to existing speaker cluster or create new
                    matched = None
                    for cl in clusters:
                        if abs(cl["cx"] - cx) < 0.09 and abs(cl["cy"] - cy) < 0.12:
                            matched = cl
                            break
                    if matched is None:
                        matched = {
                            "id": len(clusters),
                            "cx": cx,
                            "cy": cy,
                            "w": nw,
                            "h": nh,
                            "hits": 0,
                            "motion_sum": 0.0,
                        }
                        clusters.append(matched)

                    # Smoothly update cluster center
                    matched["hits"] += 1
                    matched["motion_sum"] += motion_val
                    alpha = 0.2
                    matched["cx"] = matched["cx"] * (1 - alpha) + cx * alpha
                    matched["cy"] = matched["cy"] * (1 - alpha) + cy * alpha
                    matched["w"] = matched["w"] * (1 - alpha) + nw * alpha
                    matched["h"] = matched["h"] * (1 - alpha) + nh * alpha

                    detected_boxes.append({"cluster_id": matched["id"], "motion": motion_val})

            if detected_boxes:
                active = max(detected_boxes, key=lambda b: b["motion"])
                frame_events.append({"t": t_sec, "cluster_id": active["cluster_id"]})

            prev_gray = gray
        frame_idx += 1

    cap.release()

    # Keep only persistent speakers (seen in at least 15% of sampled frames)
    min_hits = max(2, int((duration_sec * sample_fps) * 0.12))
    valid_clusters = [c for c in clusters if c["hits"] >= min_hits]
    valid_clusters.sort(key=lambda c: c["motion_sum"] / max(1, c["hits"]), reverse=True)

    # Expand face box into a comfortable head+shoulders portrait crop box (9:8 or 1:1 normalized)
    def expand_crop_box(cl: Dict[str, Any], aspect_w_over_h: float = 0.85) -> Dict[str, float]:
        # Scale box up ~2.6x around the face so shoulders & framing look natural
        ch = min(0.80, max(0.28, cl["h"] * 3.0))
        cw = min(0.80, max(0.22, ch * aspect_w_over_h * (src_h / max(1, src_w))))
        x0 = max(0.0, min(1.0 - cw, cl["cx"] - cw / 2.0))
        y0 = max(0.0, min(1.0 - ch, cl["cy"] - ch * 0.42))
        return {"x": round(x0, 3), "y": round(y0, 3), "w": round(cw, 3), "h": round(ch, 3)}

    speakers = []
    cluster_box_map = {}
    for cl in valid_clusters:
        crop = expand_crop_box(cl)
        cluster_box_map[cl["id"]] = crop
        speakers.append({
            "id": cl["id"],
            "cx": round(cl["cx"], 3),
            "cy": round(cl["cy"], 3),
            "activity": round(cl["motion_sum"] / max(1, cl["hits"]), 2),
            "box": crop,
        })

    # Smooth timeline segments (merge switches shorter than 2.5s)
    timeline_segments: List[Dict[str, Any]] = []
    if frame_events and cluster_box_map:
        cur_cid = frame_events[0]["cluster_id"]
        if cur_cid not in cluster_box_map and speakers:
            cur_cid = speakers[0]["id"]
        seg_start = 0.0
        for ev in frame_events:
            cid = ev["cluster_id"]
            if cid not in cluster_box_map:
                continue
            if cid != cur_cid and (ev["t"] - seg_start) >= 2.8:
                timeline_segments.append({
                    "start": round(seg_start, 2),
                    "end": round(ev["t"], 2),
                    "box": cluster_box_map[cur_cid],
                })
                cur_cid = cid
                seg_start = ev["t"]
        timeline_segments.append({
            "start": round(seg_start, 2),
            "end": round(duration_sec, 2),
            "box": cluster_box_map.get(cur_cid, speakers[0]["box"]) if speakers else {"x": 0.25, "y": 0.0, "w": 0.5, "h": 1.0},
        })

    rec_layout = "blur_bg"
    if len(speakers) == 2:
        rec_layout = "duo_split"
    elif len(speakers) >= 3:
        rec_layout = "speaker_focus"
    elif len(speakers) == 1:
        rec_layout = "centered_face"

    return {
        "speakers": speakers,
        "timeline_segments": timeline_segments,
        "recommended_layout": rec_layout,
        "duration_sec": round(duration_sec, 2),
    }
