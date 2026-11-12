"""
Test sans materiel : publie une fausse mesure, au meme format que la
station de liaison (STM32 -> ESP32), sur le broker MQTT.

Avec Docker :
    docker compose exec web python test_mqtt.py

Sans Docker (broker sur ton PC) :
    python test_mqtt.py 127.0.0.1
"""
import json
import random
import sys
import time

import paho.mqtt.client as mqtt

host = sys.argv[1] if len(sys.argv) > 1 else "mosquitto"

temp = round(random.uniform(18, 26), 2)
hum = round(random.uniform(30, 60), 2)
csv = (
    f"{int(time.time())},0,7,,1,8,1.2,45.3786,-71.9266,250,0,3,"
    f"1.2,4.6,7.4,8.8,0,5.4,8.9,9.5,9.6,{temp},{hum},0,0,1,,,0.02,0.03,"
    f"2500,2500,2500,2500,4394"
)
payload = {
    "station_id": 11, "src": 11, "seq": 0, "mid": random.randint(1, 10**6),
    "hop": 0, "rssi": -50, "snr": 8, "csv": csv,
}

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(host, 1883, 60)
client.loop_start()
info = client.publish("envirosense/station/1/data", json.dumps(payload))
info.wait_for_publish()
client.loop_stop()
client.disconnect()
print(f"Publie sur {host} : station 11, temperature={temp} °C, humidite={hum} %")
