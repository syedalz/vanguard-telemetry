from paho.mqtt import client as mqtt_client
import time
import random
import json
from datetime import datetime, timezone




class AssetNode:

    NORMAL_RANGES = {

        "engine_temp_c": (85,95),
        "hyd_pressure_bar": (140,170),
        "vibration_mm_s":(2,5),
        "fuel_pct": (50,95)
    }


    # How much each value jitters per tick (standard deviation)
    NOISE = {
        "engine_temp_c": 0.3,
        "hyd_pressure_bar": 1.5,
        "vibration_mm_s": 0.15,
    }
    
    # Fraction of the gap to the normal midpoint closed each tick
    PULL = 0.05
    
    # Chance per tick of dropping offline, and how many ticks an outage lasts
    OFFLINE_CHANCE = 0.02
    OFFLINE_TICKS = (3, 10)

    def __init__(self,asset_id,asset_type,broker_host,port):

        self.asset_id = asset_id
        self.asset_type = asset_type
        self.broker_host = broker_host
        self.port = port
        topic = "fleet/" + asset_type + "/" + asset_id + "/telemetry"
        self.topic = topic
        self.engine_temp_c = random.uniform(*self.NORMAL_RANGES["engine_temp_c"])
        self.hyd_pressure_bar = random.uniform(*self.NORMAL_RANGES["hyd_pressure_bar"])
        self.vibration_mm_s = random.uniform(*self.NORMAL_RANGES["vibration_mm_s"])
        self.fuel_pct = random.uniform(*self.NORMAL_RANGES["fuel_pct"])
        self.offline_ticks_left = 0

    
    def drift(self, value, key):
        low, high = self.NORMAL_RANGES[key]
        middle = (low + high) / 2
        return value + self.PULL * (middle - value) + random.gauss(0, self.NOISE[key])

    def tick(self):
        self.engine_temp_c = self.drift(self.engine_temp_c, "engine_temp_c")
        self.hyd_pressure_bar = self.drift(self.hyd_pressure_bar, "hyd_pressure_bar")
        self.vibration_mm_s = max(0, self.drift(self.vibration_mm_s, "vibration_mm_s"))
        self.fuel_pct = max(0, self.fuel_pct - random.uniform(0.005, 0.02))

    def connect_mqtt(self):

        def on_connect( client,userdata,flags,reason_code,properties):

            if reason_code == 0:
                print("Connected to MQTT Broker!")
            else:
                print(f"Failed to connect, return code {reason_code}")


        client = mqtt_client.Client(client_id="vanguard-" + self.asset_id, callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
        )       

        client.on_connect = on_connect
        client.connect(self.broker_host, self.port)
        self.client = client


    def build_payload(self, seq):
        return json.dumps({
            "asset_id": self.asset_id,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "seq": seq,
            "engine_temp_c": round(self.engine_temp_c, 2),
            "hyd_pressure_bar": round(self.hyd_pressure_bar, 1),
            "vibration_mm_s": round(self.vibration_mm_s, 2),
            "fuel_pct": round(self.fuel_pct, 2),
        })

    def publish(self):
        seq = 1

        try:
            while True:
                time.sleep(1)
                self.tick()

                if self.offline_ticks_left == 0 and random.random() < self.OFFLINE_CHANCE:
                    self.offline_ticks_left = random.randint(*self.OFFLINE_TICKS)
                    print(f"Going offline for {self.offline_ticks_left} ticks")

                if self.offline_ticks_left > 0:
                    print(f"Offline, not sending seq {seq}")
                    self.offline_ticks_left -= 1
                    if self.offline_ticks_left == 0:
                        print("Back online")
                else:
                    msg = self.build_payload(seq)
                    result = self.client.publish(self.topic, msg)
                    status = result[0]
                    if status == 0:
                        print(f"Sent `{msg}` to topic `{self.topic}`")
                    else:
                        print(f"Failed to send message to topic {self.topic}")
                seq += 1
        except KeyboardInterrupt:
            print("Ctrl+C received, shutting down...")

    def run(self):

        self.connect_mqtt()
        self.client.loop_start()
        self.publish()
        self.client.disconnect()
        self.client.loop_stop()
        print("Disconnected cleanly.")
        
