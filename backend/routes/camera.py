from fastapi import APIRouter, HTTPException
import cv2

from backend.app_state import parking_system


router = APIRouter(
    prefix="/camera",
    tags=["Camera"]
)


camera = None


@router.post("/start")
def start_camera():

    global camera

    if camera is not None:
        return {
            "message": "Camera is already running"
        }

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        camera = None

        raise HTTPException(
            status_code=500,
            detail="Could not open camera"
        )

    return {
        "message": "Camera started"
    }


@router.post("/stop")
def stop_camera():

    global camera

    if camera is not None:
        camera.release()
        camera = None

    return {
        "message": "Camera stopped"
    }


@router.get("/status")
def camera_status():

    return {
        "running": camera is not None
    }

@router.post("/process")
def process_camera_frame():

    if camera is None:
        raise HTTPException(
            status_code=400,
            detail="Camera is not running"
        )

    success, frame = camera.read()

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Could not read camera frame"
        )

    result = parking_system.process_frame(
        frame
    )

    return result