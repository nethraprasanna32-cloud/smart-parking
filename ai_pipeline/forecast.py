"""Occupancy forecasting: seasonal baseline and optional LSTM (python -m ai_pipeline.forecast --help)."""

import argparse
import json
import math
import os
import random
from datetime import datetime, timedelta
from statistics import mean, pstdev


BUCKET_MINUTES = 15
LSTM_WEIGHTS = os.getenv("FORECAST_LSTM_WEIGHTS", "models/forecast_lstm.pt")


def parse_history(history):
    points = []
    for item in history or []:
        try:
            points.append((
                datetime.fromisoformat(str(item["timestamp"])),
                float(item["occupied"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    points.sort(key=lambda point: point[0])
    return points


def resample(points, step_minutes, end=None):
    if not points:
        return []

    step = timedelta(minutes=step_minutes)
    start = points[0][0].replace(second=0, microsecond=0)
    start -= timedelta(minutes=start.minute % step_minutes)
    end = end or points[-1][0]

    grid = []
    index = 0
    current = points[0][1]
    moment = start
    while moment <= end:
        while index < len(points) and points[index][0] <= moment:
            current = points[index][1]
            index += 1
        grid.append((moment, current))
        moment += step

    while index < len(points) and points[index][0] <= end:
        current = points[index][1]
        index += 1
    if current != grid[-1][1]:
        grid.append((end, current))

    return grid


def _sigmoid(x):
    return 1 / (1 + math.exp(-x))


def _day_shape(hour, kind, arrive, leave):
    if kind == "weekday":
        inside = _sigmoid((hour - arrive) / 0.45) * (1 - _sigmoid((hour - leave) / 0.55))
        lunch = 0.12 * math.exp(-((hour - 13.0) / 0.7) ** 2)
        return 0.05 + 0.82 * inside - lunch
    peak = 0.55 if kind == "saturday" else 0.35
    return 0.04 + peak * math.exp(-((hour - 14.0) / 3.0) ** 2)


def synthetic_history(days=56, capacity=50, step_minutes=BUCKET_MINUTES,
                      end=None, seed=None):
    rng = random.Random(seed)
    capacity = max(1, int(capacity))
    step = timedelta(minutes=step_minutes)
    end = (end or datetime.now()).replace(second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % step_minutes)
    moment = end - timedelta(days=days)

    history = []
    noise = 0.0
    day = None
    while moment <= end:
        if moment.date() != day:
            day = moment.date()
            kind = ("weekday",) * 5 + ("saturday", "sunday")
            kind = kind[moment.weekday()]
            if kind == "weekday" and rng.random() < 0.04:
                kind = "sunday"
            busyness = rng.gauss(1.0, 0.08)
            arrive = rng.gauss(8.25, 0.25)
            leave = rng.gauss(17.75, 0.35)

        hour = moment.hour + moment.minute / 60
        noise = 0.8 * noise + rng.gauss(0, 0.025)
        fraction = _day_shape(hour, kind, arrive, leave) * busyness + noise
        occupied = round(min(1.0, max(0.0, fraction)) * capacity)
        history.append({"timestamp": moment.isoformat(), "occupied": occupied})
        moment += step
    return history


def _bucket(moment):
    return moment.weekday(), (moment.hour * 60 + moment.minute) // BUCKET_MINUTES


def _ewma(values, alpha=0.5):
    level = values[0]
    for value in values[1:]:
        level = alpha * value + (1 - alpha) * level
    return level


class SeasonalBaseline:
    name = "baseline"

    def __init__(self):
        self.trained_points = []

    def train(self, history, epochs=None):
        points = parse_history(history)
        if not points:
            raise ValueError("Training history has no valid {timestamp, occupied} rows.")
        self.trained_points = points
        return {"samples": len(points)}

    def predict(self, history, horizon_minutes=60, now=None, capacity=None):
        points = sorted(
            self.trained_points + parse_history(history),
            key=lambda point: point[0]
        )
        if not points:
            return {"predicted": 0.0, "low": 0.0, "high": 0.0}

        now = now or datetime.now()
        level = _ewma([value for _, value in points[-6:]])
        target = now + timedelta(minutes=horizon_minutes)

        grid = resample(points, BUCKET_MINUTES, end=now)
        weekday, slot = _bucket(target)
        same_slot_and_day = [v for t, v in grid if _bucket(t) == (weekday, slot)]
        same_slot = [v for t, v in grid if _bucket(t)[1] == slot]
        samples = same_slot_and_day if len(same_slot_and_day) >= 2 else same_slot

        if len(samples) >= 2:
            weight = (1 - math.exp(-horizon_minutes / 60)) * min(1.0, len(samples) / 4)
            predicted = (1 - weight) * level + weight * mean(samples)
            spread = pstdev(samples)
        else:
            predicted = level
            steps = [b - a for (_, a), (_, b) in zip(grid, grid[1:])]
            spread = (pstdev(steps) if len(steps) > 1 else 0.0) * math.sqrt(
                max(1.0, horizon_minutes / BUCKET_MINUTES)
            )

        spread = max(0.5, spread)
        return {
            "predicted": max(0.0, predicted),
            "low": max(0.0, predicted - 1.28 * spread),
            "high": predicted + 1.28 * spread,
        }


def _features(moment, value, scale):
    minutes = moment.hour * 60 + moment.minute
    day_angle = 2 * math.pi * minutes / 1440
    week_angle = 2 * math.pi * moment.weekday() / 7
    return [
        value / scale,
        math.sin(day_angle),
        math.cos(day_angle),
        math.sin(week_angle),
        math.cos(week_angle),
    ]


def _build_network(torch):
    class OccupancyLSTM(torch.nn.Module):
        def __init__(self, hidden=32):
            super().__init__()
            self.lstm = torch.nn.LSTM(5, hidden, batch_first=True)
            self.head = torch.nn.Linear(hidden, 1)

        def forward(self, x):
            output, _ = self.lstm(x)
            return self.head(output[:, -1]).squeeze(-1)

    return OccupancyLSTM()


class LSTMForecaster:
    name = "lstm"

    def __init__(self, weights_path=LSTM_WEIGHTS, load=True):
        import torch

        self.torch = torch
        self.weights_path = weights_path
        self.network = _build_network(torch)
        self.scale = 1.0
        self.seq_len = 16
        self.step_minutes = BUCKET_MINUTES
        self.horizon_steps = 4
        self.residual_std = 0.5

        if load:
            if not os.path.isfile(weights_path):
                raise FileNotFoundError(
                    f"LSTM weights not found at {weights_path}. "
                    "Train them with: python -m ai_pipeline.forecast train"
                )
            checkpoint = torch.load(weights_path, map_location="cpu")
            self.network.load_state_dict(checkpoint["state_dict"])
            for key in ("scale", "seq_len", "step_minutes", "horizon_steps", "residual_std"):
                setattr(self, key, checkpoint[key])
        self.network.eval()

    @property
    def horizon_minutes(self):
        return self.horizon_steps * self.step_minutes

    def train(self, history, epochs=200, capacity=None):
        torch = self.torch
        grid = resample(parse_history(history), self.step_minutes)
        window = self.seq_len + self.horizon_steps
        if len(grid) <= window:
            raise ValueError(
                f"Need more than {window} resampled points "
                f"({window * self.step_minutes} minutes of history) to train the LSTM."
            )

        self.scale = float(capacity or max(1.0, max(value for _, value in grid)))
        features = [_features(t, v, self.scale) for t, v in grid]
        targets = [v / self.scale for _, v in grid]

        inputs = torch.tensor(
            [features[i:i + self.seq_len] for i in range(len(grid) - window + 1)],
            dtype=torch.float32
        )
        labels = torch.tensor(
            [targets[i + window - 1] for i in range(len(grid) - window + 1)],
            dtype=torch.float32
        )

        self.network.train()
        optimizer = torch.optim.Adam(self.network.parameters(), lr=0.01)
        loss_fn = torch.nn.MSELoss()
        for _ in range(int(epochs)):
            optimizer.zero_grad()
            loss = loss_fn(self.network(inputs), labels)
            loss.backward()
            optimizer.step()
        self.network.eval()

        final_loss = loss.item()
        self.residual_std = max(0.5, math.sqrt(final_loss) * self.scale)
        return {"samples": len(labels), "loss": final_loss}

    def save(self):
        os.makedirs(os.path.dirname(self.weights_path) or ".", exist_ok=True)
        self.torch.save({
            "state_dict": self.network.state_dict(),
            "scale": self.scale,
            "seq_len": self.seq_len,
            "step_minutes": self.step_minutes,
            "horizon_steps": self.horizon_steps,
            "residual_std": self.residual_std,
        }, self.weights_path)

    def predict(self, history, horizon_minutes=None, now=None, capacity=None):
        grid = resample(parse_history(history), self.step_minutes, end=now or datetime.now())
        if len(grid) < self.seq_len:
            raise ValueError("Not enough history for the LSTM yet.")

        scale = float(capacity or self.scale)
        window = [_features(t, v, scale) for t, v in grid[-self.seq_len:]]
        with self.torch.no_grad():
            output = self.network(self.torch.tensor([window], dtype=self.torch.float32))
        predicted = max(0.0, float(output[0]) * scale)
        spread = self.residual_std * scale / self.scale

        return {
            "predicted": predicted,
            "low": max(0.0, predicted - 1.28 * spread),
            "high": predicted + 1.28 * spread,
        }


def _load_history(args):
    if args.synthetic:
        return synthetic_history(args.days, args.capacity, seed=args.seed)

    if args.input:
        with open(args.input, encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("history", data) if isinstance(data, dict) else data

    from urllib.request import urlopen

    url = args.from_api.rstrip("/") + "/dashboard/occupancy-history?limit=20000"
    with urlopen(url, timeout=10) as response:
        return json.load(response)["history"]


def split_history(history, holdout_days):
    points = parse_history(history)
    cutoff = points[-1][0] - timedelta(days=holdout_days)
    rows = [{"timestamp": t.isoformat(), "occupied": v} for t, v in points]
    return [r for r, (t, _) in zip(rows, points) if t < cutoff], rows


def evaluate(models, history, holdout_days=7, horizon_minutes=60, capacity=None, every=2):
    points = parse_history(history)
    cutoff = points[-1][0] - timedelta(days=holdout_days)
    horizon = timedelta(minutes=horizon_minutes)
    actual = dict(points)
    errors = {model.name: [] for model in models}

    moments = [t for t, _ in points if t >= cutoff and t + horizon in actual]
    for moment in moments[::every]:
        past = [
            {"timestamp": t.isoformat(), "occupied": v}
            for t, v in points if moment - timedelta(hours=6) <= t <= moment
        ]
        for model in models:
            result = model.predict(past, horizon_minutes, now=moment, capacity=capacity)
            errors[model.name].append(abs(result["predicted"] - actual[moment + horizon]))

    return {name: round(mean(values), 2) for name, values in errors.items() if values}


def main():
    parser = argparse.ArgumentParser(description="Train the optional occupancy LSTM.")
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="Train and save LSTM weights")
    source = train.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="JSON list of {timestamp, occupied}")
    source.add_argument("--from-api", help="Backend base URL, e.g. http://localhost:8000")
    source.add_argument("--synthetic", action="store_true", help="Train on generated data")
    train.add_argument("--epochs", type=int, default=300)
    train.add_argument("--out", default=LSTM_WEIGHTS)
    train.add_argument(
        "--holdout-days", type=int, default=7,
        help="Train without the last N days, then score both models on them (0 = off)"
    )

    generate = sub.add_parser("synthetic", help="Write generated history to a JSON file")
    generate.add_argument("--out", default="synthetic_history.json")

    for command in (train, generate):
        command.add_argument("--days", type=int, default=56)
        command.add_argument("--capacity", type=int, default=50)
        command.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    if args.command == "synthetic":
        history = synthetic_history(args.days, args.capacity, seed=args.seed)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(history, handle)
        print(f"Wrote {len(history)} snapshots ({args.days} days, "
              f"{args.capacity} spaces) -> {args.out}")
        return

    history = _load_history(args)
    capacity = args.capacity if args.synthetic else None
    train_rows = history
    if args.holdout_days:
        older, history = split_history(history, args.holdout_days)
        if len(older) >= len(history) // 2:
            train_rows = older
        else:
            print("Not enough history to hold days out; training on all of it.")

    model = LSTMForecaster(weights_path=args.out, load=False)
    result = model.train(train_rows, epochs=args.epochs, capacity=capacity)
    model.save()
    print(f"Trained on {result['samples']} windows, loss {result['loss']:.4f} -> {args.out}")

    if train_rows is not history:
        baseline = SeasonalBaseline()
        baseline.train(train_rows)
        scores = evaluate([model, baseline], history, args.holdout_days, capacity=capacity)
        print(f"1-hour-ahead error on the held-out {args.holdout_days} days "
              "(average spaces off): " + ", ".join(f"{k} {v}" for k, v in scores.items()))


if __name__ == "__main__":
    main()
