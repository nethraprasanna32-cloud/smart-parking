import os
import threading

from ai_pipeline.detect_and_ocr import (
    ALPRService,
    LicensePlateDetector,
    OCREngine,
    fix_indian_plate,
    is_valid_plate,
    normalize_plate,
)


# A plate written on paper is ordinary text, not a photo of a real plate, so
# it's read with EasyOCR rather than the plate model. The plate test page and
# the gates (in paper-plate mode) share this one reader.
_text_reader = None
text_reader_lock = threading.Lock()

# Whole camera frames are shrunk to this width before reading paper plates.
PAPER_FRAME_WIDTH = 960


def get_text_reader():
    global _text_reader
    with text_reader_lock:
        if _text_reader is None:
            _text_reader = OCREngine(simulated=False, engine="easyocr")
        return _text_reader


def clean_plate(text):
    """Return (raw, plate): the read without spaces, and with look-alikes fixed."""
    raw = normalize_plate(text)
    plate = fix_indian_plate(raw) if os.getenv("PLATE_REGION", "IN").upper() == "IN" else raw
    return raw, plate


def best_plate(fragments, longest_run=4):
    """Find a plate among text fragments; a frame also holds stray words.

    Tries each run of up to `longest_run` neighbouring fragments (a plate is
    often read as "MH14" + "AB1234") and keeps the surest one that looks like
    a plate. Returns (raw, plate, confidence) or None.
    """
    best = None
    for start in range(len(fragments)):
        for end in range(start + 1, min(len(fragments), start + longest_run) + 1):
            run = fragments[start:end]
            raw, plate = clean_plate("".join(text for text, _ in run))
            if not is_valid_plate(plate):
                continue
            confidence = min(conf for _, conf in run)
            if best is None or confidence > best[2]:
                best = (raw, plate, confidence)
    return best


class ALPRManager:

    def __init__(self):
        self.alpr = None
        self.simulated = True

    def configure(self, simulated=True):
        # Build both parts before swapping so a failed load keeps the old pipeline.
        plate_detector = LicensePlateDetector(simulated=simulated)
        ocr = OCREngine(simulated=simulated)

        self.alpr = ALPRService(
            plate_detector=plate_detector,
            ocr=ocr
        )
        self.simulated = simulated

    def recognize_plates(self, frame, known_plates=None):
        if self.alpr is None:
            return []

        return self.alpr.detect_and_recognize(
            frame,
            known_plates=known_plates
        )

    def read_paper_plate(self, frame, min_confidence=0.4):
        """Read a plate written on paper anywhere in the frame; no plate box needed."""
        if frame is None or frame.size == 0:
            return []

        import cv2

        height, width = frame.shape[:2]
        image = frame
        if width > PAPER_FRAME_WIDTH:
            scale = PAPER_FRAME_WIDTH / width
            image = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

        reader = get_text_reader()
        with text_reader_lock:
            fragments = reader.read_fragments(image)

        found = best_plate(fragments)
        if found is None or found[2] < min_confidence:
            return []

        raw, plate, confidence = found
        return [{
            "plate_text": plate,
            "raw_text": raw,
            "confidence": round(confidence, 3),
            "bbox": [0, 0, width, height],
        }]
