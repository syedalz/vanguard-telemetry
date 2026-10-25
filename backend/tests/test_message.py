import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.telemetry import TelemetryMessage


def valid_payload(**overrides):
    # A known-good message; tests pass overrides to break one field at a time
    payload = {
        "asset_id": "truck-01",
        "asset_type": "haul_truck",
        "timestamp": "2026-10-22T18:36:55.116-06:00",
        "seq": 1,
        "engine_temp_c": 90.0,
        "hyd_pressure_bar": 155.0,
        "vibration_mm_s": 3.5,
        "fuel_pct": 70.0,
    }
    payload.update(overrides)
    return payload


def parse(payload):
    # Go through JSON, the way real messages arrive
    return TelemetryMessage.model_validate_json(json.dumps(payload))


def test_valid_message():
    msg = parse(valid_payload())
    assert msg.asset_id == "truck-01"
    assert msg.seq == 1
    assert msg.fuel_pct == 70.0


def test_timestamp_keeps_offset():
    # The -06:00 offset is kept and still converts to the right UTC instant
    msg = parse(valid_payload())
    assert msg.timestamp.utcoffset() == timedelta(hours=-6)
    assert msg.timestamp.astimezone(timezone.utc) == datetime(2026, 10, 23, 0, 36, 55, 116000, tzinfo=timezone.utc)


def test_parses_simulator_json():
    # Raw string copied from the simulator's output
    raw = '{"asset_id": "truck-01", "asset_type": "haul_truck", "timestamp": "2026-10-22T18:36:55.116-06:00", "seq": 1, "engine_temp_c": 91.7, "hyd_pressure_bar": 153.1, "vibration_mm_s": 2.25, "fuel_pct": 64.11}'
    msg = TelemetryMessage.model_validate_json(raw)
    assert msg.engine_temp_c == 91.7


@pytest.mark.parametrize("field", [
    "asset_id", "asset_type", "timestamp", "seq",
    "engine_temp_c", "hyd_pressure_bar", "vibration_mm_s", "fuel_pct",
])
def test_missing_field_rejected(field):
    payload = valid_payload()
    del payload[field]
    with pytest.raises(ValidationError):
        parse(payload)


@pytest.mark.parametrize("field", [
    "gps", "location", "weather", "company",
    "driver",
])
def test_added_field_rejected(field):
    # extra="forbid" rejects any field not in the model
    payload = valid_payload()
    payload[field] = 'abc'
    with pytest.raises(ValidationError):
        parse(payload)


# Values right at the edge of each allowed range
@pytest.mark.parametrize("field, value", [
    ("seq", 1),
    ("engine_temp_c", -39.9),
    ("engine_temp_c", 199.9),
    ("hyd_pressure_bar", 0),
    ("vibration_mm_s", 0),
    ("fuel_pct", 0),
    ("fuel_pct", 100),
])
def test_boundary_values_accepted(field, value):
    parse(valid_payload(**{field: value}))


# Values just past each limit
@pytest.mark.parametrize("field, value", [
    ("seq", 0),
    ("seq", -1),
    ("engine_temp_c", -40),
    ("engine_temp_c", 200),
    ("hyd_pressure_bar", -0.1),
    ("vibration_mm_s", -0.1),
    ("fuel_pct", -0.1),
    ("fuel_pct", 100.1),
])
def test_out_of_range_rejected(field, value):
    with pytest.raises(ValidationError):
        parse(valid_payload(**{field: value}))


@pytest.mark.parametrize("field, value", [
    ("seq", "abc"),
    ("seq", 1.5),
    ("asset_id", ""),
    ("asset_type", "haul_trruck"),
    ("engine_temp_c", "hot"),
    # Numeric string, rejected because the field is strict
    ("engine_temp_c", "100.5"),
    ("engine_temp_c", float("nan")),
    ("timestamp", "not a date"),
    # Valid date but no UTC offset
    ("timestamp", "2026-10-22T18:36:55"),
])
def test_wrong_type_rejected(field, value):
    with pytest.raises(ValidationError):
        parse(valid_payload(**{field: value}))

