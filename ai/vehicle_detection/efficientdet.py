class EfficientDetVehicleDetector:

    def __init__(self, model=None):
        self.model = model

    def detect(self, frame):

        if self.model is None:
            raise NotImplementedError(
                "EfficientDet model is not configured yet."
            )

        return self.model.detect(frame)