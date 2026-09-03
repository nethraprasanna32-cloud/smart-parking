from ultralytics import RTDETR


class RTDETRVehicleDetector:

    def __init__(self, model_path="rtdetr-l.pt"):
        self.model = RTDETR(model_path)

        self.vehicle_classes = {
            2: "car",
            3: "motorcycle",
            5: "bus",
            7: "truck"
        }

    def detect(self, frame):

        results = self.model(frame, verbose=False)

        detections = []

        for result in results:

            if result.boxes is None:
                continue

            for box in result.boxes:

                class_id = int(box.cls[0])
                confidence = float(box.conf[0])

                if class_id not in self.vehicle_classes:
                    continue

                x1, y1, x2, y2 = box.xyxy[0].tolist()

                detections.append({
                    "type": self.vehicle_classes[class_id],
                    "confidence": confidence,
                    "bbox": [
                        int(x1),
                        int(y1),
                        int(x2),
                        int(y2)
                    ]
                })

        return detections