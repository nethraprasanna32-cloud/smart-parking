from ai_pipeline.forecast import LSTMForecaster, SeasonalBaseline


MODELS = ("baseline", "lstm")


class PredictionManager:

    def __init__(self, horizon_minutes=60):
        self.horizon_minutes = horizon_minutes
        self.baseline = SeasonalBaseline()
        self.model = self.baseline

    def change_model(self, model_type):
        if model_type not in MODELS:
            raise ValueError(
                "Unsupported prediction model. Choose baseline or lstm."
            )

        if model_type == "baseline":
            self.model = self.baseline
        elif self.model.name != "lstm":
            # Raises ImportError / FileNotFoundError and keeps the current model.
            self.model = LSTMForecaster()

    def train(self, history, epochs=200, capacity=None):
        if self.model.name == "lstm":
            result = self.model.train(history, epochs=epochs, capacity=capacity)
            self.model.save()
            return result
        return self.model.train(history, epochs=epochs)

    def forecast(self, history, capacity, now=None):
        model = self.model
        note = None
        try:
            result = model.predict(history, self.horizon_minutes, now=now, capacity=capacity)
        except ValueError as exc:
            # The LSTM needs a full input window; fall back until it has one.
            model = self.baseline
            note = str(exc)
            result = model.predict(history, self.horizon_minutes, now=now, capacity=capacity)

        def clamp(value):
            return round(min(float(capacity), max(0.0, value)), 1)

        return {
            "model": model.name,
            "horizon_minutes": self.horizon_minutes,
            "predicted_occupancy": clamp(result["predicted"]),
            "low": clamp(result["low"]),
            "high": clamp(result["high"]),
            "note": note,
        }

    def get_current_model(self):
        return self.model.name
