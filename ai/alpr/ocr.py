import cv2
import pytesseract


class OCREngine:

    def __init__(self):
        self.config = (
            "--psm 7 "
            "-c tessedit_char_whitelist="
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )

    def readtext(self, image):

        if image is None:
            return ""

        # Make sure OCR receives a valid image
        if len(image.shape) == 3:
            image = cv2.cvtColor(
                image,
                cv2.COLOR_BGR2GRAY
            )

        text = pytesseract.image_to_string(
            image,
            config=self.config
        )

        return text.strip()