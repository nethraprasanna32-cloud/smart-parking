from backend.services.alpr import ALPRService
from ai.alpr.plate_detector import LicensePlateDetector
from ai.alpr.ocr import OCREngine


class ALPRManager:

    def __init__(self):

        self.plate_detector = None
        self.ocr = OCREngine()
        self.alpr = None

    def configure(self, model_path):

        self.plate_detector = LicensePlateDetector(
            model_path=model_path
        )

        self.alpr = ALPRService(
            plate_detector=self.plate_detector,
            ocr=self.ocr
        )

    def recognize_plates(self, frame):

        if self.alpr is None:
            return []

        return self.alpr.detect_and_recognize(
            frame
        )