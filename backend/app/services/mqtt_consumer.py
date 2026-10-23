from paho.mqtt import client as mqtt_client
from app.models.telemetry import TelemetryMessage
from pydantic import ValidationError

broker = 'localhost'
port = 1883
topic = "fleet/+/+/telemetry"
client_id = "vanguard-backend"


def connect_mqtt():

    def on_message(client, userdata, msg):

        try:
            data = TelemetryMessage.model_validate_json(msg.payload)

            print(f"{data.asset_id} seq {data.seq} OK")

        except ValidationError as e:
            print(f"Rejected message from {msg.topic}: {e}")


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


def run():
    client = connect_mqtt()
    client.loop_forever()


if __name__ == '__main__':
    run()
