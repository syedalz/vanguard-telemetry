from paho.mqtt import client as mqtt_client
from app.models.telemetry import TelemetryMessage
from app.services.anomaly import check_threshold
from pydantic import ValidationError
import psycopg
from datetime import timezone
broker = 'localhost'
port = 1883
# Wildcards match every asset type and asset id, e.g. fleet/haul_truck/truck-01/telemetry
topic = "fleet/+/+/telemetry"
client_id = "vanguard-backend"

def connect_mqtt(conn, detector):
    """Build an MQTT client that validates each telemetry message and stores it via conn."""

    cur = conn.cursor()

    # A repeat of the same asset and timestamp is skipped instead of raising an error
    insert_query = """
    
        INSERT INTO telemetry_messages (asset_id, asset_type, timestamp, seq, engine_temp_c, hyd_pressure_bar, vibration_mm_s, fuel_pct)

        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)

        ON CONFLICT (asset_id, timestamp) DO NOTHING
    
    
    """

    def on_message(client, userdata, msg):

        try:

            data = TelemetryMessage.model_validate_json(msg.payload)
          
            msg_data = (data.asset_id, data.asset_type, data.timestamp, data.seq, data.engine_temp_c, data.hyd_pressure_bar, data.vibration_mm_s, data.fuel_pct)

            cur.execute(insert_query, msg_data)

            # rowcount is 0 when ON CONFLICT skipped the row
            if cur.rowcount == 1:
                ts = data.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                for r in check_threshold(data):
                    print(f"ALERT {data.asset_id} {ts} threshold {r['sensor']}={r['value']} (limit {r['limit']}, {r['direction']})")

                for r in detector.check(data):
                    print(f"ALERT {data.asset_id} {ts} zscore    {r['sensor']}={r['value']} (z={r['z_score']:.1f}, mean {r['mean']:.1f})")

            elif cur.rowcount == 0:
                print(f"Duplicate row skipped: {data.asset_id} at time {data.timestamp} ")

            

        except ValidationError as e:
            print(f"Rejected message from {msg.topic}: {e}")

        except psycopg.Error as e:
            print(f"Failed to insert message {data.asset_id}: {e} .")


       



    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print("Connected to MQTT Broker!")
            # Subscribing here means the subscription is restored after every reconnect
            client.subscribe(topic)

        else:
            print(f"Failed to connect, return code {reason_code}")

    client = mqtt_client.Client(
        client_id=client_id,
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION2,
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker, port)
    return client
