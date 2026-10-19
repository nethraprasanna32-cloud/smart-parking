def slot_name(index):
    return f"A{index:02d}"


class OccupancyManager:
    def __init__(self, capacity=4):
        self.capacity = capacity

    def set_capacity(self, capacity):
        capacity = int(capacity)
        if capacity < 0:
            raise ValueError("Parking capacity cannot be negative.")
        self.capacity = capacity

    def slot_ids(self):
        return [slot_name(index) for index in range(1, self.capacity + 1)]

    def get_slot_assignments(self, currently_parked):
        """Map plate -> slot. Stored slots win; legacy records, and cars in slots
        that no longer exist after the lot shrank, fill gaps in order."""
        assignments = {}
        used_slots = set()
        valid_slots = set(self.slot_ids())

        for vehicle in currently_parked:
            slot_id = vehicle.get("slot_id")
            if slot_id in valid_slots and slot_id not in used_slots:
                assignments[vehicle["plate_number"]] = slot_id
                used_slots.add(slot_id)

        free_slots = (
            slot_id for slot_id in self.slot_ids()
            if slot_id not in used_slots
        )
        for vehicle in currently_parked:
            if vehicle["plate_number"] not in assignments:
                slot_id = next(free_slots, None)
                if slot_id is None:
                    break
                assignments[vehicle["plate_number"]] = slot_id

        return assignments

    def get_available_slot(self, currently_parked):
        used_slots = set(self.get_slot_assignments(currently_parked).values())

        for slot_id in self.slot_ids():
            if slot_id not in used_slots:
                return slot_id

        return None

    def get_statistics(self, currently_parked):
        occupied = len(currently_parked)
        available = max(0, self.capacity - occupied)
        vehicles_by_plate = {
            vehicle["plate_number"]: vehicle
            for vehicle in currently_parked
        }
        plates_by_slot = {
            slot_id: plate_number
            for plate_number, slot_id
            in self.get_slot_assignments(currently_parked).items()
        }

        occupancy_rate = (
            (occupied / self.capacity) * 100
            if self.capacity > 0
            else 0
        )

        slots = []
        for slot_id in self.slot_ids():
            plate_number = plates_by_slot.get(slot_id)
            vehicle = vehicles_by_plate.get(plate_number, {})
            slots.append({
                "slot_id": slot_id,
                "status": "occupied" if plate_number else "available",
                "plate_number": plate_number,
                "entered_at": vehicle.get("entered_at"),
            })

        return {
            "total_slots": self.capacity,
            "occupied": occupied,
            "available": available,
            "occupancy_rate": round(occupancy_rate, 2),
            "slots": slots,
        }
