import time
import json
import uuid
import paho.mqtt.client as mqtt


def test_mqtt_connection(broker, port, username, password, topic):
    logs = []

    try:
        port = int(port)
    except ValueError:
        return ["ERROR: Port harus angka"]

    client_id = f"test-client-{uuid.uuid4().hex[:6]}"
    client = mqtt.Client(client_id=client_id)

    if username:
        client.username_pw_set(username, password)

    # ========================
    # Callback
    # ========================
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logs.append("Connected to broker")
        else:
            logs.append(f"ERROR: Failed connect, code={rc}")

    def on_publish(client, userdata, mid):
        logs.append("Message published")

    def on_disconnect(client, userdata, rc):
        logs.append("Disconnected")

    client.on_connect = on_connect
    client.on_publish = on_publish
    client.on_disconnect = on_disconnect

    try:
        logs.append(f"Connecting to {broker}:{port} ...")
        client.connect(broker, port, keepalive=5)

        client.loop_start()
        time.sleep(2)

        if not any("Connected" in l for l in logs):
            logs.append("ERROR: Tidak berhasil konek ke broker")
            client.loop_stop()
            return logs

        payload = {
            "test": True,
            "timestamp": int(time.time())
        }

        result = client.publish(topic, json.dumps(payload), qos=2)

        time.sleep(2)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logs.append(f"ERROR: Publish gagal ({result.rc})")

        client.disconnect()
        time.sleep(1)
        client.loop_stop()

    except Exception as e:
        logs.append(f"ERROR: {str(e)}")

    return logs