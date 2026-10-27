import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.telemetry import TelemetryMessage
from tests.test_message import valid_payload, parse
from app.services.anomaly import check_threshold, z_score, ZScoreDetector, AlertManager


# Checks if a healthy reading reports no breaches
def test_healthy_reading_has_no_breaches():
   check =  check_threshold(parse(valid_payload()))
   assert check == []



# Checks each threshold breach one at a time
@pytest.mark.parametrize("field, value, limit, direction", [
    ("engine_temp_c", 106, 105, "high"),
    ("hyd_pressure_bar", 134, 135, "low"),
    ("vibration_mm_s", 8, 7, "high")
])
def test_single_breach_reported(field,value, limit, direction):

    msg = parse(valid_payload(**{field: value}))
    check = check_threshold(msg)

    assert check == [{"sensor": field, "value": value, "limit": limit, "direction": direction}]
    

# Checks if reading values right on the threshold are not reported
@pytest.mark.parametrize("field, value", [
    ("engine_temp_c", 105),
    ("hyd_pressure_bar", 135),
    ("vibration_mm_s", 7)
])
def test_at_threshold_not_reported(field,value):

    msg = parse(valid_payload(**{field: value}))
    check = check_threshold(msg)

    assert check == []

# Checks if multiple threshold breaches in same reading are reported
def test_all_breaches_reported():
    msg = parse(valid_payload(engine_temp_c=106, hyd_pressure_bar=134, vibration_mm_s=8))
    check = check_threshold(msg)

    assert check == [
        {       
            "sensor": "engine_temp_c",
            "value": 106,
            "limit": 105,
            "direction": "high"
        },

        {       
            "sensor": "hyd_pressure_bar",
            "value": 134,
            "limit": 135,
            "direction": "low"
        },

         {       
            "sensor": "vibration_mm_s",
            "value": 8,
            "limit": 7,
            "direction": "high"
        },       
    ]

# Checks the z-score maths on a small window
def test_z_score_basic():
    assert z_score([9, 10, 11], 14) == 4.0


# Checks a window with no variation gives no score
def test_z_score_flat_window():
    assert z_score([10, 10, 10], 14) is None


# Checks an empty window gives no score
def test_z_score_empty_window():
    assert z_score([], 14) is None


def reading(seq, asset_id="truck-01", **overrides):
    return parse(valid_payload(asset_id=asset_id, seq=seq, **overrides))


def fill_window(detector, asset_id="truck-01"):
    # Alternate either side of the defaults so every sensor has some spread
    # (hyd_pressure_bar: mean 155, stdev about 1)
    for i in range(ZScoreDetector.WINDOW_SIZE):
        sign = 1 if i % 2 == 0 else -1
        detector.check(reading(
            i + 1,
            asset_id,
            engine_temp_c=90.0 + sign,
            hyd_pressure_bar=155.0 + sign,
            vibration_mm_s=3.5 + 0.5 * sign,
        ))
    return ZScoreDetector.WINDOW_SIZE + 1


# Checks nothing is flagged until the window is full, even a wild reading
def test_warm_up_returns_nothing():
    detector = ZScoreDetector()
    for seq in range(1, ZScoreDetector.WINDOW_SIZE):
        assert detector.check(reading(seq, hyd_pressure_bar=155.0 + seq % 2)) == []

    wild = reading(ZScoreDetector.WINDOW_SIZE, hyd_pressure_bar=10.0)
    assert detector.check(wild) == []


# Checks a normal reading after warm-up is not flagged
def test_normal_reading_after_warm_up():
    detector = ZScoreDetector()
    seq = fill_window(detector)

    assert detector.check(reading(seq, hyd_pressure_bar=155.5)) == []


# Checks a big pressure drop is flagged with a negative z-score
def test_anomaly_flagged():
    detector = ZScoreDetector()
    seq = fill_window(detector)

    res = detector.check(reading(seq, hyd_pressure_bar=140.0))

    assert len(res) == 1
    assert res[0]["sensor"] == "hyd_pressure_bar"
    assert res[0]["value"] == 140.0
    assert res[0]["z_score"] < -ZScoreDetector.CUTOFF


# Checks each truck has its own window
def test_trucks_do_not_share_windows():
    detector = ZScoreDetector()
    fill_window(detector, "truck-01")

    assert detector.check(reading(1, "truck-02", hyd_pressure_bar=1000.0)) == []


# Checks a window with no variation doesn't crash or flag anything
def test_flat_window_does_not_crash():
    detector = ZScoreDetector()
    for seq in range(1, ZScoreDetector.WINDOW_SIZE + 1):
        detector.check(reading(seq))

    assert detector.check(reading(ZScoreDetector.WINDOW_SIZE + 1, hyd_pressure_bar=140.0)) == []


# Checks the score is taken before the reading joins the window
# (if 140 were appended first, the mean would be pulled below 155)
def test_scored_before_append():
    detector = ZScoreDetector()
    seq = fill_window(detector)

    res = detector.check(reading(seq, hyd_pressure_bar=140.0))

    assert res[0]["mean"] == pytest.approx(155.0)


# Checks a vibration spike is flagged with a positive z-score
def test_positive_anomaly_flagged():
    detector = ZScoreDetector()
    seq = fill_window(detector)

    res = detector.check(reading(seq, vibration_mm_s=10.0))

    assert len(res) == 1
    assert res[0]["sensor"] == "vibration_mm_s"
    assert res[0]["value"] == 10.0
    assert res[0]["z_score"] > ZScoreDetector.CUTOFF


# Made-up check results, so these tests only exercise the alert logic
BREACH = [{"sensor": "hyd_pressure_bar"}]


def healthy_streak(manager, count, asset_id="truck-01"):
    # Sends count healthy readings and returns every event they produced
    events = []
    for i in range(count):
        events += manager.update(reading(i + 1, asset_id), [], [])
    return events


# Checks a first breach opens an alert, and a repeat breach doesn't open another
def test_breach_opens_alert_once():
    manager = AlertManager()

    events = manager.update(reading(1), BREACH, [])

    assert len(events) == 1
    assert events[0]["type"] == "opened"
    assert events[0]["sensor"] == "hyd_pressure_bar"
    assert events[0]["methods"] == {"threshold"}

    assert manager.update(reading(2), BREACH, []) == []


# Checks the alert resolves on exactly the 30th healthy reading
def test_resolves_after_recovery_readings():
    manager = AlertManager()
    manager.update(reading(1), BREACH, [])

    assert healthy_streak(manager, AlertManager.RECOVERY_READINGS - 1) == []

    events = manager.update(reading(100), [], [])

    assert len(events) == 1
    assert events[0]["type"] == "resolved"
    assert events[0]["sensor"] == "hyd_pressure_bar"


# Checks a breach mid-streak resets it, so a full 30 more are needed
def test_breach_resets_healthy_streak():
    manager = AlertManager()
    manager.update(reading(1), BREACH, [])
    healthy_streak(manager, AlertManager.RECOVERY_READINGS - 1)

    assert manager.update(reading(100), BREACH, []) == []

    assert healthy_streak(manager, AlertManager.RECOVERY_READINGS - 1) == []

    events = manager.update(reading(200), [], [])

    assert len(events) == 1
    assert events[0]["type"] == "resolved"


# Checks a method that joins an open alert is listed when it resolves
def test_resolved_lists_methods_that_joined_later():
    manager = AlertManager()
    manager.update(reading(1), [], BREACH)
    manager.update(reading(2), BREACH, [])

    events = healthy_streak(manager, AlertManager.RECOVERY_READINGS)

    assert len(events) == 1
    assert events[0]["methods"] == {"zscore", "threshold"}


# Checks the "opened" event keeps its own methods when a new method joins later
# (fails if the event and the alert share one set object)
def test_opened_event_methods_not_changed_later():
    manager = AlertManager()
    opened = manager.update(reading(1), [], BREACH)[0]

    manager.update(reading(2), BREACH, [])

    assert opened["methods"] == {"zscore"}


# Checks two trucks with the same sensor get separate alerts
def test_trucks_get_separate_alerts():
    manager = AlertManager()

    first = manager.update(reading(1, "truck-01"), BREACH, [])
    second = manager.update(reading(1, "truck-02"), BREACH, [])

    assert len(first) == 1
    assert first[0]["asset_id"] == "truck-01"
    assert len(second) == 1
    assert second[0]["asset_id"] == "truck-02"

    # Resolving truck-01 leaves truck-02's alert open
    events = healthy_streak(manager, AlertManager.RECOVERY_READINGS, "truck-01")
    assert [e["asset_id"] for e in events] == ["truck-01"]
    assert ("truck-02", "hyd_pressure_bar") in manager.open_alerts


# Checks a healthy reading with no alert open returns nothing
def test_healthy_reading_with_no_alert_returns_nothing():
    assert AlertManager().update(reading(1), [], []) == []


# Checks the resolved event's opened_at is the opening reading's timestamp
# (the opening reading gets its own timestamp, since every other reading shares the default one)
def test_resolved_opened_at_matches_opening_reading():
    manager = AlertManager()
    opening = reading(1, timestamp="2026-10-22T08:00:00.000-06:00")
    manager.update(opening, BREACH, [])

    events = healthy_streak(manager, AlertManager.RECOVERY_READINGS)

    assert events[0]["type"] == "resolved"
    assert events[0]["opened_at"] == opening.timestamp
    assert events[0]["opened_at"] != events[0]["timestamp"]
