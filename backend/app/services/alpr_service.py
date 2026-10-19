from ai_pipeline.detect_and_ocr import ALPRService, LicensePlateDetector, OCREngine


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
