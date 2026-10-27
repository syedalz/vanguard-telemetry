import statistics
from collections import deque

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



