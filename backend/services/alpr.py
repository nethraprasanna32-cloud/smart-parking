import cv2
import re
import numpy as np


class ALPRService:

    def __init__(self, plate_detector=None, ocr=None):
        self.plate_detector = plate_detector
        self.ocr = ocr

    def preprocess_plate(self, plate_image):
        """
        Prepare a license plate image for OCR.
        """

        if plate_image is None or plate_image.size == 0:
            return None

        # Convert to grayscale
        gray = cv2.cvtColor(
            plate_image,
            cv2.COLOR_BGR2GRAY
        )

        # Reduce noise
        gray = cv2.GaussianBlur(
            gray,
            (3, 3),
            0
        )

        # Improve contrast
        processed = cv2.threshold(
            gray,
            0,
            255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1]

        return processed

    def clean_plate_text(self, text):
        """
        Clean OCR output and keep
        alphanumeric characters.
        """

        if not text:
            return ""

        text = text.upper()

        # Remove spaces and special characters
        text = re.sub(
            r"[^A-Z0-9]",
            "",
            text
        )

        return text

    def recognize_plate(self, plate_image):
        """
        Run OCR on a license plate image.
        """

        if self.ocr is None:
            raise RuntimeError(
                "OCR engine is not configured."
            )

        processed = self.preprocess_plate(
            plate_image
        )

        if processed is None:
            return ""

        text = self.ocr.readtext(processed)

        return self.clean_plate_text(text)

    def detect_and_recognize(self, frame):
        """
        Detect license plates and recognize
        their text.
        """

        if self.plate_detector is None:
            raise RuntimeError(
                "License plate detector is not configured."
            )

        plates = self.plate_detector.detect(frame)

        results = []

        for plate in plates:

            x1, y1, x2, y2 = plate["bbox"]

            # Keep coordinates inside image
            height, width = frame.shape[:2]

            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(width, x2)
            y2 = min(height, y2)

            plate_image = frame[
                y1:y2,
                x1:x2
            ]

            text = self.recognize_plate(
                plate_image
            )

            results.append({
                "plate_text": text,
                "confidence": plate.get(
                    "confidence",
                    0
                ),
                "bbox": [
                    x1,
                    y1,
                    x2,
                    y2
                ]
            })

        return results