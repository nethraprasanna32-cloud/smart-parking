import numpy as np
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense


class ParkingLSTM:

    def __init__(
        self,
        sequence_length=10
    ):
        self.sequence_length = sequence_length
        self.model = self.build_model()

    def build_model(self):

        model = Sequential([
            LSTM(
                64,
                input_shape=(
                    self.sequence_length,
                    1
                )
            ),
            Dense(32, activation="relu"),
            Dense(1)
        ])

        model.compile(
            optimizer="adam",
            loss="mse"
        )

        return model

    def prepare_data(self, occupancy_data):
        """
        Convert historical occupancy data
        into sequences for LSTM.
        """

        X = []
        y = []

        for i in range(
            len(occupancy_data)
            - self.sequence_length
        ):

            sequence = occupancy_data[
                i:i + self.sequence_length
            ]

            target = occupancy_data[
                i + self.sequence_length
            ]

            X.append(sequence)
            y.append(target)

        X = np.array(X)
        y = np.array(y)

        X = X.reshape(
            X.shape[0],
            X.shape[1],
            1
        )

        return X, y

    def train(
        self,
        occupancy_data,
        epochs=20
    ):

        X, y = self.prepare_data(
            occupancy_data
        )

        self.model.fit(
            X,
            y,
            epochs=epochs,
            verbose=1
        )

    def predict(
        self,
        recent_data
    ):

        data = np.array(
            recent_data
        )

        data = data.reshape(
            1,
            self.sequence_length,
            1
        )

        prediction = self.model.predict(
            data,
            verbose=0
        )

        return float(prediction[0][0])