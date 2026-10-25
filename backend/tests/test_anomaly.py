import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.telemetry import TelemetryMessage
from tests.test_message import valid_payload, parse
from app.services.anomaly import check_threshold


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