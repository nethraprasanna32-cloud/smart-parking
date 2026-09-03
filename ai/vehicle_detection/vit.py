class VisionTransformerVehicleDetector:

    def __init__(self, model=None):
        self.model = model

    def detect(self, frame):

        if self.model is None:
            raise NotImplementedError(
                "Vision Transformer model is not configured yet."
            )

        return self.model.detect(frame)