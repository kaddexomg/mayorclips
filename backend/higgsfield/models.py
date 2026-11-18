from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class CameraMotionType(str, Enum):
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    ORBIT_3D = "orbit_3d"
    STATIC = "static"

class CameraControl(BaseModel):
    motion: CameraMotionType = Field(default=CameraMotionType.ZOOM_IN, description="Tipo de movimiento cinematográfico de cámara")
    speed: float = Field(default=1.0, ge=0.1, le=3.0, description="Velocidad del movimiento")
    strength: float = Field(default=0.7, ge=0.1, le=1.0, description="Intensidad de la trayectoria")

class VideoGenerationRequest(BaseModel):
    prompt: str = Field(description="Descripción de la escena cinematográfica")
    camera: CameraControl = Field(default_factory=CameraControl)
    aspect_ratio: str = Field(default="9:16", description="Relación de aspecto: 9:16 para Reels/TikTok, 16:9 para YouTube")
    duration_sec: float = Field(default=4.0, ge=2.0, le=10.0)
    seed: Optional[int] = None
    higgsfield_model: Optional[str] = "cinema-studio-v2"
