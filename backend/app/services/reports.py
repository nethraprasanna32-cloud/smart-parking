from collections import defaultdict
from datetime import date, datetime, timedelta


REJECTED = {"entry_rejected", "capacity_full"}


def daily_report(database, days=7, today=None):
    """Per-day counts, busiest moment and average stay, oldest day first."""
    today = today or date.today()
    first_day = today - timedelta(days=days - 1)
    since = first_day.isoformat()

    # Stores return newest first. Reverse before the (stable) sort so events
    # with identical timestamps stay in the order they happened.
    events = database.get_events(100000, since=since)[::-1]
    events.sort(key=lambda event: event["timestamp"])
    snapshots = database.get_occupancy_between(since)

    rows = {
        (first_day + timedelta(days=offset)).isoformat(): {
            "date": (first_day + timedelta(days=offset)).isoformat(),
            "entries": 0,
            "exits": 0,
            "turned_away": 0,
            "stolen_seen": 0,
            "peak_occupancy": 0,
            "peak_at": None,
            "average_stay_minutes": None,
            "_stays": [],
        }
        for offset in range(days)
    }

    # Pair each exit with the plate's most recent entry to measure stays.
    entered_at = {}
    for event in events:
        row = rows.get(event["timestamp"][:10])
        if row is None:
            continue
        if event["status"] == "entered":
            row["entries"] += 1
            entered_at[event["plate_number"]] = event["timestamp"]
        elif event["status"] == "exited":
            row["exits"] += 1
            start = entered_at.pop(event["plate_number"], None)
            if start:
                minutes = (
                    datetime.fromisoformat(event["timestamp"]) - datetime.fromisoformat(start)
                ).total_seconds() / 60
                row["_stays"].append(minutes)
        elif event["status"] in REJECTED:
            row["turned_away"] += 1
        if event.get("security_status") == "STOLEN":
            row["stolen_seen"] += 1

    for snapshot in snapshots:
        row = rows.get(snapshot["timestamp"][:10])
        if row and snapshot["occupied"] > row["peak_occupancy"]:
            row["peak_occupancy"] = snapshot["occupied"]
            row["peak_at"] = snapshot["timestamp"]

    result = []
    for row in rows.values():
        stays = row.pop("_stays")
        if stays:
            row["average_stay_minutes"] = round(sum(stays) / len(stays))
        result.append(row)
    return result


def summarize(rows):
    totals = defaultdict(int)
    for row in rows:
        for key in ("entries", "exits", "turned_away", "stolen_seen"):
            totals[key] += row[key]
    busiest = max(rows, key=lambda row: row["peak_occupancy"], default=None)
    return {
        **totals,
        "busiest_day": busiest["date"] if busiest and busiest["peak_occupancy"] else None,
    }
