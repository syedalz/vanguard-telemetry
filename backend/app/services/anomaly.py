THRESHOLDS = {
    "engine_temp_c":    {"limit": 105, "direction": "high"},
    "hyd_pressure_bar": {"limit": 135, "direction": "low"},
    "vibration_mm_s":   {"limit": 7,   "direction": "high"},
}

def check_threshold(msg):

    res = []

    for sensor, rule in THRESHOLDS.items():

        val = getattr(msg, sensor)
        breached = False

        if rule["direction"] == "high":
            breached = val > rule["limit"]

        else:
            breached = val < rule["limit"]

        if breached:
            res.append({       
            "sensor": sensor,
            "value": val,
            "limit": rule["limit"],
            "direction": rule["direction"]
            })
        
    return res