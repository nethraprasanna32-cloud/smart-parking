import os
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.app.services.gate_camera import VIDEO_EXTENSIONS
from backend.app.state import cameras


router = APIRouter(
    prefix="/camera",
    tags=["Camera"]
)


class CameraStartRequest(BaseModel):
    source: Optional[str] = Field(
        default="0",
        description="Webcam index, video file path, or stream URL (e.g. http://<esp32-ip>/stream)",
    )
    fps: float = Field(default=2.0, gt=0, le=30, description="Frames processed per second")


def get_camera(gate):
    if gate not in cameras:
        raise HTTPException(
            status_code=404,
            detail="Unknown gate. Use entry or exit."
        )
    return cameras[gate]


@router.get("/test-videos")
def list_test_videos():
    directory = os.path.join(os.getcwd(), "test_videos")
    if not os.path.isdir(directory):
        return {"videos": []}

    videos = []
    for root, _, filenames in os.walk(directory):
        for filename in sorted(filenames):
            if os.path.splitext(filename)[1].lower() not in VIDEO_EXTENSIONS:
                continue
            relative = os.path.relpath(os.path.join(root, filename), os.getcwd()).replace("\\", "/")
            folder = os.path.relpath(root, directory).replace("\\", "/")
            videos.append({
                "filename": filename,
                "label": filename if folder == "." else f"{folder}/{filename}",
                "path": relative,
            })

    videos.sort(key=lambda video: video["label"])
    return {"videos": videos}


@router.get("/")
def all_camera_status():
    return {gate: camera.status() for gate, camera in cameras.items()}


@router.post("/{gate}/start")
def start_camera(gate: str, request: Optional[CameraStartRequest] = None):
    camera = get_camera(gate)
    request = request or CameraStartRequest()

    try:
        camera.start(request.source, fps=request.fps)
    except ImportError as exc:
        raise HTTPException(503, "OpenCV is not installed. Install opencv-python.") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc

    return camera.status()


@router.post("/{gate}/stop")
def stop_camera(gate: str):
    camera = get_camera(gate)
    camera.stop()
    return camera.status()


@router.get("/{gate}/status")
def camera_status(gate: str):
    return get_camera(gate).status()


@router.post("/{gate}/process")
def process_camera_frame(gate: str):
    """Process one frame now. With no source running this is a simulated read."""
    camera = get_camera(gate)
    try:
        return camera.process_once()
    except (ImportError, FileNotFoundError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/{gate}/snapshot.jpg")
def camera_snapshot(gate: str):
    camera = get_camera(gate)
    if camera.latest_jpeg is None:
        raise HTTPException(404, "No frame captured yet.")
    return Response(
        camera.latest_jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{gate}/stream")
def camera_stream(gate: str):
    camera = get_camera(gate)

    def frames():
        last = None
        idle_since = time.monotonic()
        while True:
            jpeg = camera.latest_jpeg
            if jpeg is not None and jpeg is not last:
                last = jpeg
                idle_since = time.monotonic()
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + jpeg
                    + b"\r\n"
                )
            elif not camera.running and time.monotonic() - idle_since > 2:
                return
            time.sleep(0.1)

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
