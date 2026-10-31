import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import psycopg

GROUND_TRUTH_PATH = Path(__file__).resolve().parent.parent / "ground_truth.jsonl"
CONNECTION_URI = "postgresql://vanguard:vanguard@localhost:5432/telemetry"

alerts_query = """

    SELECT asset_id, sensor, opened_at
    FROM alerts
    WHERE sensor != 'heartbeat'
    ORDER BY opened_at

"""


def load_ground_truth(path):
    """Read the JSON lines file into a list of event dicts."""
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def pair_faults(events):
    """Match each fault_started with the next serviced record for the same truck.

    A truck only has one fault at a time, so we track the open fault per truck.
    Faults that were never serviced (sim stopped mid-fault) get serviced_at = None.
    """
    open_faults = {}
    pairs = []

    for event in events:
        truck = event["asset_id"]

        if event["event"] == "fault_started":
            pair = {
                "asset_id": truck,
                "fault": event["fault"],
                "sensor": event["sensor"],
                "started_at": datetime.fromisoformat(event["timestamp"]),
                "serviced_at": None,
            }
            open_faults[truck] = pair
            pairs.append(pair)

        elif event["event"] == "serviced":
            pair = open_faults.pop(truck, None)
            if pair is None:
                print(f"Warning: {truck} serviced at {event['timestamp']} with no open fault")
                continue
            pair["serviced_at"] = datetime.fromisoformat(event["timestamp"])

    return pairs


def load_alerts(conninfo):
    """Fetch sensor alerts (no heartbeats), grouped by (asset_id, sensor).

    Same key the detector uses for its windows, so each list holds the alerts
    for one truck's sensor, oldest first. Missing keys give an empty list.
    """
    alerts = defaultdict(list)

    with psycopg.connect(conninfo) as conn:
        for asset_id, sensor, opened_at in conn.execute(alerts_query):
            alerts[(asset_id, sensor)].append(opened_at)

    return alerts


def match_alerts(pairs, alerts):
    """Set delay_s on each serviced fault: seconds until its first alert, or None if missed.

    Faults that were never serviced are left out, since their outcome isn't known yet.
    """
    serviced = [p for p in pairs if p["serviced_at"] is not None]

    for p in serviced:
        p["delay_s"] = None
        # .get so a sensor with no alerts doesn't add an empty entry to the defaultdict
        for opened_at in alerts.get((p["asset_id"], p["sensor"]), []):
            if p["started_at"] <= opened_at <= p["serviced_at"]:
                p["delay_s"] = (opened_at - p["started_at"]).total_seconds()
                break

    return serviced


def print_summary(results):
    """Print one row per fault type: total, caught (with %), and median/max delay of the caught ones."""
    delays_by_fault = defaultdict(list)
    for p in results:
        delays_by_fault[p["fault"]].append(p["delay_s"])

    print(f"{'fault':<16} {'faults':>6}  {'caught':<10} {'median':>7} {'max':>7}")
    for fault, delays in sorted(delays_by_fault.items()):
        caught = [d for d in delays if d is not None]
        pct = 100 * len(caught) / len(delays)
        caught_text = f"{len(caught)} ({pct:.0f}%)"

        # median() raises on an empty list, so a type with no catches gets dashes
        if caught:
            median = f"{statistics.median(caught):.1f}s"
            longest = f"{max(caught):.1f}s"
        else:
            median = longest = "-"

        print(f"{fault:<16} {len(delays):>6}  {caught_text:<10} {median:>7} {longest:>7}")


def main():
    events = load_ground_truth(GROUND_TRUTH_PATH)
    pairs = pair_faults(events)
    alerts = load_alerts(CONNECTION_URI)
    results = match_alerts(pairs, alerts)

    skipped = len(pairs) - len(results)
    print(f"{len(results)} serviced faults ({skipped} never serviced, left out)")
    print()

    print(f"{'truck':<10} {'fault':<16} {'sensor':<18} {'start':<32} delay")
    for p in results:
        delay = "MISSED" if p["delay_s"] is None else f"{p['delay_s']:.1f}s"
        print(f"{p['asset_id']:<10} {p['fault']:<16} {p['sensor']:<18} {str(p['started_at']):<32} {delay}")

    print()
    print_summary(results)


if __name__ == "__main__":
    main()
