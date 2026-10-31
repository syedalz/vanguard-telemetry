from paho.mqtt import client as mqtt_client
import random
import json
from datetime import datetime, timezone
import threading

class AssetNode:
    """One simulated fleet asset that drifts its sensor values and publishes them to MQTT."""

    # Healthy (low, high) range for each sensor; starting values are drawn from these
    NORMAL_RANGES = {

        "engine_temp_c": (85,95),
        "hyd_pressure_bar": (140,170),
        "vibration_mm_s":(2,5),
        "fuel_pct": (50,95)
    }

    # Refuel when fuel drops below this, back up to a random level in this range.
    REFUEL_RANGE_PCT = (80,99)
    REFUEL_BELOW_PCT = 10


    # How much each value jitters per tick (standard deviation)
    NOISE = {
        "engine_temp_c": 0.3,
        "hyd_pressure_bar": 1.5,
        "vibration_mm_s": 0.15,
    }

    # Stores which fault corresponds to which sensor
    FAULT_SENSORS= {

        "coolant_leak": "engine_temp_c",
        "hydraulic_leak": "hyd_pressure_bar",
        "worn_parts": "vibration_mm_s"
    }

    # Fraction of the gap to the normal midpoint closed each tick
    PULL = 0.05

    # Chance per tick of dropping offline, and how many ticks an outage lasts
    OFFLINE_CHANCE = 0.002
    OFFLINE_TICKS = (3, 10)

    # Chance per tick of a fault starting, how many ticks it lasts, and how each fault distorts its sensor
    FAULT_CHANCE = 0.05
    DURATION_RANGE = (10,20)
    COOLANT_CLIMB_RATE_C = (0.3, 0.5)
    COOLANT_MAX_TEMP_C = 120
    HYD_LEAK_EXTRA_DROP_CHANCE = 0.003
    HYD_LEAK_DROP_BAR = (25, 50)
    HYD_MIN_PRESSURE_BAR = 5
    WEAR_SPIKE_MM_S = (7,12)
    WEAR_SPIKE_CHANCE = 0.15
    LOG_LOCK = threading.Lock()

    def __init__(self,asset_id,asset_type,broker_host,port):

        self.asset_id = asset_id
        self.asset_type = asset_type
        self.broker_host = broker_host
        self.port = port
        # e.g. fleet/haul_truck/truck-01/telemetry
        topic = "fleet/" + asset_type + "/" + asset_id + "/telemetry"
        self.topic = topic
        # Start each sensor at a random point inside its normal range
        self.engine_temp_c = random.uniform(*self.NORMAL_RANGES["engine_temp_c"])
        self.hyd_pressure_bar = random.uniform(*self.NORMAL_RANGES["hyd_pressure_bar"])
        self.vibration_mm_s = random.uniform(*self.NORMAL_RANGES["vibration_mm_s"])
        self.fuel_pct = random.uniform(*self.NORMAL_RANGES["fuel_pct"])
        # Ticks remaining in the current outage; 0 means online
        self.offline_ticks_left = 0
        # Fault state; fault_type None means healthy
        self.fault_type = None
        self.fault_offset = 0
        self.fault_ticks_elapsed = 0
        self.fault_duration = None

    def log_ground_truth(self, event, timestamp):

        """Writes faults and service alerts to a JSON lines file"""

        with self.LOG_LOCK:
            fault_dict = {"event": event, "asset_id": self.asset_id, "fault": self.fault_type, "sensor": self.FAULT_SENSORS[self.fault_type], "timestamp": timestamp}
            
            with open("ground_truth.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(fault_dict) + "\n")




    def drift(self, value, key):
        """Return the next value: pulled toward the range midpoint, plus random noise."""
        low, high = self.NORMAL_RANGES[key]
        middle = (low + high) / 2
        return value + self.PULL * (middle - value) + random.gauss(0, self.NOISE[key])

    def tick(self, timestamp):
        """Advance all sensor values by one time step."""
        self.engine_temp_c = self.drift(self.engine_temp_c, "engine_temp_c")
        self.hyd_pressure_bar = self.drift(self.hyd_pressure_bar, "hyd_pressure_bar")
        # Vibration can't be negative
        self.vibration_mm_s = max(0, self.drift(self.vibration_mm_s, "vibration_mm_s"))
        # Fuel only ever goes down, and refuels below 10%
        self.fuel_pct = max(0, self.fuel_pct - random.uniform(0.005, 0.02))
        if self.fuel_pct < self.REFUEL_BELOW_PCT:
            self.fuel_pct = random.uniform(*self.REFUEL_RANGE_PCT)

        if (self.fault_type is None) and (random.random() < self.FAULT_CHANCE):
            self.fault_type = random.choice(list(self.FAULT_SENSORS.keys()))
            self.fault_duration = random.randint(*self.DURATION_RANGE)
            self.fault_ticks_elapsed = 0

            print(f"{self.asset_id}: {self.fault_type} started at {timestamp}")
            self.log_ground_truth("fault_started", timestamp)

           

        if self.fault_type is not None:
            self.fault_ticks_elapsed +=1
            
            if (self.fault_type == "coolant_leak"):
                self.fault_offset += random.uniform(*self.COOLANT_CLIMB_RATE_C)
                reported_temp = (self.engine_temp_c + self.fault_offset)
                if reported_temp > self.COOLANT_MAX_TEMP_C:
                    self.fault_offset = self.COOLANT_MAX_TEMP_C - self.engine_temp_c

            elif (self.fault_type == "hydraulic_leak"):
               
                if (self.fault_ticks_elapsed == 1) or (random.random() < self.HYD_LEAK_EXTRA_DROP_CHANCE):
                    self.fault_offset -= random.uniform(*self.HYD_LEAK_DROP_BAR)

                reported_pressure = self.hyd_pressure_bar + self.fault_offset
                   
                if (reported_pressure < self.HYD_MIN_PRESSURE_BAR):
                    self.fault_offset = self.HYD_MIN_PRESSURE_BAR - self.hyd_pressure_bar


            elif (self.fault_type == "worn_parts"):

                if (random.random() < self.WEAR_SPIKE_CHANCE):

                    self.fault_offset = random.uniform(*self.WEAR_SPIKE_MM_S)

                else:
                    self.fault_offset = 0

            if (self.fault_ticks_elapsed >= self.fault_duration):
                print(f"{self.asset_id}: {self.fault_type} serviced at {timestamp}")
                self.log_ground_truth("serviced", timestamp)
                self.fault_type = None
                self.fault_offset = 0
                self.fault_ticks_elapsed = 0
                self.fault_duration = None

            



    def connect_mqtt(self):
        """Create this asset's MQTT client and connect it to the broker."""

        def on_connect( client,userdata,flags,reason_code,properties):

            if reason_code == 0:
                print(f"{self.asset_id}: Connected to MQTT Broker!")
            else:
                print(f"{self.asset_id}: Failed to connect, return code {reason_code}")


        # Client IDs must be unique per broker, so include the asset ID
        client = mqtt_client.Client(client_id="vanguard-" + self.asset_id, callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
        )

        client.on_connect = on_connect
        client.connect(self.broker_host, self.port)
        self.client = client


    def build_payload(self, seq, timestamp):
        """Return the current reading as a JSON string."""

        payload_dict = {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            # ISO 8601 in UTC with an explicit +00:00 offset
            "timestamp": timestamp,
            # Rises by one every reading, so the backend can spot lost messages
            "seq": seq,
            "engine_temp_c": round(self.engine_temp_c, 2),
            "hyd_pressure_bar": round(self.hyd_pressure_bar, 2),
            "vibration_mm_s": round(self.vibration_mm_s, 2),
            "fuel_pct": round(self.fuel_pct, 2),
        }


        if self.fault_type is not None:

            sensor = self.FAULT_SENSORS[self.fault_type]
            payload_dict[sensor] += self.fault_offset
            payload_dict[sensor] = round(payload_dict[sensor],2)

        
        return json.dumps(payload_dict)

    def publish(self,event):
        """Tick and publish once a second until the stop event is set."""
        seq = 1

        # wait(1) sleeps up to 1s and returns True as soon as the event is set
        while not event.wait(1):
            current_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            self.tick(current_time)

            # Maybe start a new outage (only while online)
            if self.offline_ticks_left == 0 and random.random() < self.OFFLINE_CHANCE:
                self.offline_ticks_left = random.randint(*self.OFFLINE_TICKS)
                print(f"{self.asset_id}: Going offline for {self.offline_ticks_left} ticks")

            # While offline, skip publishing but keep ticking and counting seq
            if self.offline_ticks_left > 0:
                print(f"{self.asset_id}: Offline, not sending seq {seq}")
                self.offline_ticks_left -= 1
                if self.offline_ticks_left == 0:
                    print(f"{self.asset_id}: Back online")
            else:
                msg = self.build_payload(seq,current_time)
                result = self.client.publish(self.topic, msg)
                status = result[0]
                if status != 0:
                    print(f"{self.asset_id}: Failed to send message to topic {self.topic}")
            # Always advance seq, so outages show up as jumps
            seq += 1


    def run(self, event):
        """Connect, publish until the stop event is set, then disconnect."""

        self.connect_mqtt()
        # Run the MQTT network loop in a background thread
        self.client.loop_start()
        self.publish(event)
        # Disconnect before stopping the loop so the DISCONNECT packet is actually sent
        self.client.disconnect()
        self.client.loop_stop()
        print(f"{self.asset_id}: Disconnected cleanly.")

