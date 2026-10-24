from paho.mqtt import client as mqtt_client
from app.models.telemetry import TelemetryMessage
from pydantic import ValidationError
import psycopg
broker = 'localhost'
port = 1883
topic = "fleet/+/+/telemetry"
client_id = "vanguard-backend"

def connect_mqtt(conn):

    cur = conn.cursor()

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

            if cur.rowcount == 1:
                print(f"{data.asset_id} seq {data.seq} OK")

            elif cur.rowcount == 0:
                print(f"Duplicate row skipped: {data.asset_id} at time {data.timestamp} ")

        except ValidationError as e:
            print(f"Rejected message from {msg.topic}: {e}")

        except psycopg.Error as e:
            print(f"Failed to insert message {data.asset_id}: {e} .")



    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print("Connected to MQTT Broker!")
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
