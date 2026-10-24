import itertools
import os
import re
from difflib import get_close_matches


VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
}

PLATE_PATTERNS = {
    "IN": re.compile(r"^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{4}$"),
    "ANY": re.compile(r"^[A-Z0-9]{4,10}$"),
}

SIMULATED_PLATES = [
    "MH12AB1234",
    "TN09BC4321",
    "MH14XY9087",
    "KA01AB0001",
    "DL8CAF5031",
]


def normalize_plate(text):
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def is_valid_plate(plate_number, region=None):
    region = (region or os.getenv("PLATE_REGION", "IN")).upper()
    pattern = PLATE_PATTERNS.get(region, PLATE_PATTERNS["IN"])
    return bool(pattern.match(plate_number or ""))


AS_DIGIT = str.maketrans("OQDIZSBGT", "000125867")
AS_LETTER = str.maketrans("012568", "OIZSGB")


def fix_indian_plate(plate_number):
    """Fix O/0, Z/2, S/5 look-alikes by position in the Indian layout AA 99 AAA 9999."""
    length = len(plate_number or "")
    for district in (2, 1):
        series = length - 6 - district
        if not 0 <= series <= 3:
            continue
        candidate = (
            plate_number[:2].translate(AS_LETTER)
            + plate_number[2:2 + district].translate(AS_DIGIT)
            + plate_number[2 + district:length - 4].translate(AS_LETTER)
            + plate_number[length - 4:].translate(AS_DIGIT)
        )
        if is_valid_plate(candidate, "IN"):
            return candidate
    return plate_number


def snap_plate(plate_number, known_plates, cutoff=0.82):
    if not plate_number or not known_plates:
        return None
    if plate_number in known_plates:
        return plate_number

    matches = get_close_matches(
        plate_number,
        list(known_plates),
        n=1,
        cutoff=cutoff,
    )
    return matches[0] if matches else None


MODELS_DIR = "models"


def weights_path(name):
    local = os.path.join(MODELS_DIR, name)
    return local if os.path.isfile(local) else name


def _require_weights(model_path):
    # Ultralytics silently downloads unknown names; only stock names may be fetched.
    if os.path.sep in model_path or "/" in model_path:
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"Model weights not found: {model_path}")


class SimulatedVehicleDetector:
    def detect(self, frame=None):
        return [
            {
                "type": "car",
                "confidence": 0.98,
                "bbox": [24, 28, 180, 140],
            },
        ]


class YOLO11VehicleDetector:
    default_weights = "yolo11n.pt"

    def __init__(self, model_path=None):
        from ultralytics import YOLO

        model_path = model_path or os.getenv("DETECTOR_MODEL") or weights_path(self.default_weights)
        _require_weights(model_path)
        self.model = YOLO(model_path)

    def detect(self, frame):
        if frame is None:
            return []

        results = self.model(frame, verbose=False)
        detections = []

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                class_id = int(box.cls[0])

                if class_id not in VEHICLE_CLASSES:
                    continue

                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append({
                    "type": VEHICLE_CLASSES[class_id],
                    "confidence": float(box.conf[0]),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                })

        return detections


class RTDETRVehicleDetector(YOLO11VehicleDetector):
    default_weights = "rtdetr-l.pt"

    def __init__(self, model_path=None):
        from ultralytics import RTDETR

        model_path = model_path or weights_path(self.default_weights)
        _require_weights(model_path)
        self.model = RTDETR(model_path)


DETECTORS = {
    "simulated": SimulatedVehicleDetector,
    "yolo11": YOLO11VehicleDetector,
    "rtdetr": RTDETRVehicleDetector,
}


class VehicleDetectionManager:
    def __init__(self, model_type="simulated"):
        self.detector = None
        self.model_type = None
        self.change_model(model_type)

    def change_model(self, model_type):
        if model_type not in DETECTORS:
            raise ValueError(
                "Unsupported model type. Choose "
                + ", ".join(DETECTORS)
                + "."
            )

        detector = DETECTORS[model_type]()
        self.detector = detector
        self.model_type = model_type

    @property
    def simulated(self):
        return self.model_type == "simulated"

    def detect(self, frame=None):
        return self.detector.detect(frame)


class LicensePlateDetector:
    def __init__(self, model_path=None, simulated=True):
        self.simulated = simulated
        self.model = None

        if not simulated:
            from ultralytics import YOLO

            model_path = model_path or os.getenv("PLATE_MODEL_PATH") or weights_path(
                "license_plate_detector.pt"
            )
            if not os.path.isfile(model_path):
                raise FileNotFoundError(
                    f"Plate model not found: {model_path}"
                )
            self.model = YOLO(model_path)

    def detect(self, frame=None):
        if self.simulated:
            return [{"confidence": 0.95, "bbox": [48, 102, 146, 128]}]

        if frame is None:
            return []

        detections = []
        results = self.model(frame, verbose=False)

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                detections.append({
                    "confidence": float(box.conf[0]),
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                })

        return detections


def _pick_ocr_engine(requested):
    requested = (requested or os.getenv("OCR_ENGINE", "auto")).lower()
    if requested != "auto":
        return requested
    try:
        import fast_plate_ocr  # noqa: F401
        return "fast-plate-ocr"
    except ImportError:
        return "easyocr"


class OCREngine:
    def __init__(self, simulated=True, engine=None):
        self.simulated = simulated
        self.engine = "simulated" if simulated else _pick_ocr_engine(engine)
        self.reader = None
        self._simulated_plates = itertools.cycle(SIMULATED_PLATES)

        if self.engine == "fast-plate-ocr":
            from fast_plate_ocr import LicensePlateRecognizer

            self.reader = LicensePlateRecognizer(
                os.getenv("OCR_MODEL", "cct-s-v2-global-model"),
                device="cpu",
            )
        elif self.engine == "easyocr":
            import easyocr

            self.reader = easyocr.Reader(["en"], verbose=False)
        elif self.engine != "simulated":
            raise ValueError("OCR_ENGINE must be auto, fast-plate-ocr or easyocr.")

    @staticmethod
    def prepare(image):
        import cv2

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        height = gray.shape[0]
        if height < 64:
            scale = 64 / max(1, height)
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        return gray

    def readtext(self, image=None):
        if self.simulated:
            return next(self._simulated_plates), 0.99

        if image is None or image.size == 0:
            return "", 0.0

        if self.engine == "fast-plate-ocr":
            return self._read_fast_plate(image)
        return self._read_easyocr(image)

    def _read_fast_plate(self, image):
        import cv2

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        prediction = self.reader.run(rgb, return_confidence=True)[0]
        probs = list(prediction.char_probs) if prediction.char_probs is not None else []
        confidence = float(sum(probs) / len(probs)) if probs else 0.0
        return prediction.plate, confidence

    def read_fragments(self, image):
        results = self.reader.readtext(
            self.prepare(image),
            allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        )
        results.sort(key=lambda item: (item[0][0][1] // 10, item[0][0][0]))
        return [(fragment, float(conf)) for _, fragment, conf in results]

    def _read_easyocr(self, image):
        fragments = self.read_fragments(image)
        if not fragments:
            return "", 0.0

        text = "".join(fragment for fragment, _ in fragments)
        confidence = min(conf for _, conf in fragments)

        return text, confidence


class ALPRService:
    def __init__(self, plate_detector=None, ocr=None, min_confidence=0.4):
        self.plate_detector = plate_detector or LicensePlateDetector()
        self.ocr = ocr or OCREngine()
        self.min_confidence = min_confidence

    def detect_and_recognize(self, frame=None, known_plates=None):
        results = []

        for plate in self.plate_detector.detect(frame):
            plate_image = None

            if frame is not None:
                x1, y1, x2, y2 = plate["bbox"]
                height, width = frame.shape[:2]
                plate_image = frame[
                    max(0, y1):min(height, y2),
                    max(0, x1):min(width, x2)
                ]

            raw_text, ocr_confidence = self.ocr.readtext(plate_image)
            plate_text = normalize_plate(raw_text)

            if not plate_text or ocr_confidence < self.min_confidence:
                continue

            matched = snap_plate(plate_text, known_plates or ())
            if matched:
                plate_text = matched
            elif not is_valid_plate(plate_text):
                continue

            results.append({
                "plate_text": plate_text,
                "raw_text": raw_text,
                "confidence": round(
                    min(plate.get("confidence", 0), ocr_confidence),
                    3
                ),
                "bbox": plate["bbox"],
            })

        return results
