import statistics
from collections import deque, defaultdict
import threading
from datetime import datetime, timezone


class ZScoreDetector:

    SENSORS = ["engine_temp_c", "hyd_pressure_bar", "vibration_mm_s"]
    WINDOW_SIZE = 100
    CUTOFF = 4

    def __init__(self):
        self.windows = {}


    def check(self, msg):

        res = []

        for sensor in self.SENSORS:

            val = getattr(msg,sensor)
            key = (msg.asset_id, sensor)
            
            if key not in self.windows:
                self.windows[key] = deque(maxlen=self.WINDOW_SIZE)   

            window = self.windows[key]
            if len(window) == self.WINDOW_SIZE:
                score = z_score(window, val)
                if score is not None and (abs(score) > self.CUTOFF):
                   
                    res.append({

                        "sensor": sensor,
                        "value": val,
                        "z_score": score,
                        "mean": statistics.mean(window)
                    })

            window.append(val)


        return res


class AlertManager:

    SENSORS = ["engine_temp_c", "hyd_pressure_bar", "vibration_mm_s"]

    RECOVERY_READINGS = 30

    STALE_AFTER_SECONDS = 20


    def __init__(self):
        self.open_alerts = {}
        self.last_seen = {}
        self.lock = threading.Lock()


    def update(self, msg, threshold_results, zscore_results):

        with self.lock:
            breaches = defaultdict(set)
            for r in threshold_results:
                breaches[r["sensor"]].add("threshold")

            for r in zscore_results:
                breaches[r["sensor"]].add("zscore")

            events = []

            for sensor in self.SENSORS:
                key = (msg.asset_id,sensor)
                is_open = key in self.open_alerts
                breached = sensor in breaches

                if breached and not is_open:
                    self.open_alerts[key] = {"opened_at": msg.timestamp, "methods": set(breaches[sensor]), "healthy_streak": 0}
                    events.append({
                        "type": "opened",
                        "asset_id": msg.asset_id,
                        "sensor": sensor,
                        "timestamp": msg.timestamp,        
                        "value": getattr(msg, sensor),    
                        "methods": set(breaches[sensor]),
                    })
                
                elif breached and is_open:
                    self.open_alerts[key]["healthy_streak"] = 0
                    self.open_alerts[key]["methods"] |= breaches[sensor]


                elif is_open and not breached:
                    self.open_alerts[key]["healthy_streak"] +=1
                    if self.open_alerts[key]["healthy_streak"] >= self.RECOVERY_READINGS:
                        alert = self.open_alerts.pop(key)
                        events.append({
                            "type": "resolved",
                            "asset_id": msg.asset_id,
                            "sensor": sensor,
                            "timestamp": msg.timestamp,        
                            "value": getattr(msg, sensor),    
                            "opened_at": alert["opened_at"],                  
                            "methods": alert["methods"],          
                        })


            return events

    def seen(self, asset_id, now):


        with self.lock:

            events = []

            if asset_id not in self.last_seen:
                self.last_seen[asset_id] = now

            last = self.last_seen[asset_id]
            seconds_silent = (now - last).total_seconds()
            self.last_seen[asset_id] = now
    
            key = (asset_id, "heartbeat")
            if key in self.open_alerts:
                alert = self.open_alerts.pop(key)
                events.append({
                    "type": "resolved",
                    "asset_id": asset_id,
                    "sensor": "heartbeat",
                    "timestamp": now,                 
                    "value":seconds_silent,
                    "opened_at": alert["opened_at"],
                    "methods": alert["methods"],
                })

            return events

    def check_stale(self, now):

        with self.lock:

            events = []

            for asset_id in self.last_seen:

                seconds_silent = (now - self.last_seen[asset_id]).total_seconds()
                key = (asset_id, 'heartbeat')
                
                if seconds_silent > self.STALE_AFTER_SECONDS and (key not in self.open_alerts):
                    self.open_alerts[key] = {"opened_at": now, "methods": {"stale"}, "healthy_streak": 0}

                    events.append({
                        "type": "opened",
                        "asset_id": asset_id,
                        "sensor": "heartbeat",
                        "timestamp": now,                 
                        "value": seconds_silent,
                        "opened_at": now,
                        "methods": set(self.open_alerts[key]["methods"]),
                    })

            return events





            

            


            

            









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


def z_score(window,val):

    result = len(set(window)) <= 1

    # return None if window has no variation
    if result:
        return None
    
    mean = statistics.mean(window)
    std = statistics.stdev(window)
    return ((val - mean) / std)



