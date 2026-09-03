class PredictionManager:

    def __init__(
        self,
        model_type="lstm",
        sequence_length=10
    ):
        self.model_type = model_type
        self.sequence_length = sequence_length
        self.model = None

    def _load_model(self):

        if self.model_type == "lstm":

            from ai.prediction.lstm import ParkingLSTM

            self.model = ParkingLSTM(
                sequence_length=self.sequence_length
            )

        elif self.model_type == "transformer":

            from ai.prediction.transformer import ParkingTransformer

            self.model = ParkingTransformer(
                sequence_length=self.sequence_length
            )

        else:

            raise ValueError(
                "Unsupported prediction model. "
                "Choose lstm or transformer."
            )

    def change_model(self, model_type):

        if model_type not in [
            "lstm",
            "transformer"
        ]:
            raise ValueError(
                "Unsupported prediction model. "
                "Choose lstm or transformer."
            )

        self.model_type = model_type
        self.model = None

    def train(
        self,
        occupancy_data,
        epochs=20
    ):

        if self.model is None:
            self._load_model()

        self.model.train(
            occupancy_data,
            epochs=epochs
        )

    def predict(self, recent_occupancy):

        if len(recent_occupancy) != self.sequence_length:
            raise ValueError(
                f"Prediction requires exactly "
                f"{self.sequence_length} historical values."
            )

        if self.model is None:
            self._load_model()

        return self.model.predict(
            recent_occupancy
        )

    def get_current_model(self):
        return self.model_type