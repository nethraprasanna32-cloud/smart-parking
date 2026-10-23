"""Plate-reading test bench for the webcam page.

Reads text from one image and returns it. Nothing is recorded, no gate
opens and the parking state is never touched.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from ai_pipeline.detect_and_ocr import is_valid_plate
# EasyOCR, shared with the gates' paper-plate mode, not the gate plate model.
from backend.app.services.alpr_service import clean_plate, get_text_reader as get_engine, text_reader_lock


router = APIRouter(prefix="/plate-test", tags=["Plate test"])

MAX_IMAGE_BYTES = 4 * 1024 * 1024


def read_image(data):
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("That isn't an image the server can read. Send a JPEG or PNG.")

    engine = get_engine()
    with text_reader_lock:
        text, confidence = engine.readtext(image)

    raw, plate = clean_plate(text)
    return {
        "plate_number": plate,
        "raw": raw,
        "confidence": round(float(confidence), 3),
        "looks_like_plate": is_valid_plate(plate),
    }


@router.post("/read")
async def read_plate(request: Request):
    """Send one JPEG/PNG as the request body; get back the text read from it."""
    data = await request.body()
    if not data:
        raise HTTPException(400, "No image was sent.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "The image is too large (4 MB at most).")

    try:
        return await run_in_threadpool(read_image, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(
            503,
            "EasyOCR isn't installed. Run: pip install -r ai_pipeline/requirements.txt",
        ) from exc
