from ai.prediction.lstm import ParkingLSTM


class PredictionService:

    def __init__(self):
        self.model = ParkingLSTM(
            sequence_length=10
        )

    def predict_occupancy(
        self,
        recent_occupancy
    ):
        """
        Predict future parking occupancy.

        recent_occupancy should contain
        10 historical occupancy values.
        """

        if len(recent_occupancy) != 10:
            raise ValueError(
                "Prediction requires exactly "
                "10 historical values."
            )

        return self.model.predict(
            recent_occupancy
        )