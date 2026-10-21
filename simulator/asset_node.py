from paho.mqtt import client as mqtt_client
import time



class AssetNode:
    def __init__(self,asset_id,asset_type,broker_host,port):

        self.asset_id = asset_id
        self.asset_type = asset_type
        self.broker_host = broker_host
        self.port = port
        topic = "fleet/" + asset_type + "/" + asset_id + "/telemetry"
        self.topic = topic

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


    def publish(self):
        msg_count = 1
        while True:
            time.sleep(1)   
            msg = f"messages: {msg_count}"
            result = self.client.publish(self.topic, msg)
            status = result[0]
            if status == 0:
                print(f"Sent `{msg}` to topic `{self.topic}`")
            else:
                print(f"Failed to send message to topic {self.topic}")
            msg_count += 1
            if msg_count > 5:
                break

    def run(self):

        self.connect_mqtt()
        self.client.loop_start()
        self.publish()
        self.client.loop_stop()
        self.client.disconnect()
        

if __name__ == '__main__':

    asset = AssetNode("truck-01","haul_truck", "localhost", 1883)
    asset.run()
