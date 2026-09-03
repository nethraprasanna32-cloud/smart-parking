import numpy as np

from tensorflow.keras.models import Model
from tensorflow.keras.layers import (
    Input,
    Dense,
    LayerNormalization,
    MultiHeadAttention,
    GlobalAveragePooling1D
)


class ParkingTransformer:

    def __init__(
        self,
        sequence_length=10,
        features=1
    ):
        self.sequence_length = sequence_length
        self.features = features
        self.model = self.build_model()

    def transformer_block(
        self,
        inputs,
        embedding_dim=64,
        num_heads=4
    ):

        attention = MultiHeadAttention(
            num_heads=num_heads,
            key_dim=embedding_dim
        )(
            inputs,
            inputs
        )

        attention = LayerNormalization()(
            inputs + attention
        )

        dense = Dense(
            embedding_dim,
            activation="relu"
        )(attention)

        dense = Dense(
            embedding_dim
        )(dense)

        output = LayerNormalization()(
            attention + dense
        )

        return output

    def build_model(self):

        inputs = Input(
            shape=(
                self.sequence_length,
                self.features
            )
        )

        x = Dense(64)(inputs)

        x = self.transformer_block(x)

        x = GlobalAveragePooling1D()(x)

        x = Dense(
            32,
            activation="relu"
        )(x)

        outputs = Dense(1)(x)

        model = Model(
            inputs=inputs,
            outputs=outputs
        )

        model.compile(
            optimizer="adam",
            loss="mse"
        )

        return model

    def prepare_data(
        self,
        occupancy_data
    ):

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
            self.features
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
            self.features
        )

        prediction = self.model.predict(
            data,
            verbose=0
        )

        return float(
            prediction[0][0]
        )