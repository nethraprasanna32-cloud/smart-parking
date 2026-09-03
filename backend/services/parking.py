class ParkingSlotManager:

    def __init__(self, slots=None):
        self.slots = slots or []

    def set_slots(self, slots):
        self.slots = slots

    def calculate_iou(self, box1, box2):

        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])

        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        intersection_width = max(
            0,
            x2 - x1
        )

        intersection_height = max(
            0,
            y2 - y1
        )

        intersection_area = (
            intersection_width *
            intersection_height
        )

        area1 = (
            (box1[2] - box1[0]) *
            (box1[3] - box1[1])
        )

        area2 = (
            (box2[2] - box2[0]) *
            (box2[3] - box2[1])
        )

        union_area = (
            area1 +
            area2 -
            intersection_area
        )

        if union_area == 0:
            return 0

        return intersection_area / union_area

    def check_slot_occupancy(
        self,
        vehicle_detections
    ):

        results = []

        for slot in self.slots:

            slot_box = [
                slot["x1"],
                slot["y1"],
                slot["x2"],
                slot["y2"]
            ]

            occupied = False

            for vehicle in vehicle_detections:

                iou = self.calculate_iou(
                    slot_box,
                    vehicle["bbox"]
                )

                if iou >= 0.20:
                    occupied = True
                    break

            results.append({
                "slot_id": slot["id"],
                "occupied": occupied,
                "status": (
                    "OCCUPIED"
                    if occupied
                    else "FREE"
                )
            })

        return results

    def get_statistics(
        self,
        slot_results
    ):

        total_slots = len(
            slot_results
        )

        occupied = sum(
            1
            for slot in slot_results
            if slot["occupied"]
        )

        available = (
            total_slots -
            occupied
        )

        occupancy_rate = (
            (occupied / total_slots) * 100
            if total_slots > 0
            else 0
        )

        return {
            "total_slots": total_slots,
            "occupied": occupied,
            "available": available,
            "occupancy_rate": round(
                occupancy_rate,
                2
            )
        }