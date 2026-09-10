import json
from datetime import datetime

import paho.mqtt.client as mqtt
from django.conf import settings
from django.utils import timezone

from .models import Station, Sensor, Data


def _parse_timestamp(ts):
    if not ts:
        return timezone.now()

    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    except Exception:
        return timezone.now()


def _get_or_create_station(station_id):
    station, _ = Station.objects.get_or_create(
        id_stat=str(station_id),
        defaults={
            "last_position": "---",
            "is_Sat": False,
            "is_Wifi": True,
            "is_Lora": True,
            "is_LTE": False,
            "artefacts": "",
        },
    )
    return station


def _get_or_create_sensor(station, sensor_name, unit="", sensor_type="generic", freq=0):
    sensor_id = f"{station.id_stat}_{sensor_name}"
    sensor, _ = Sensor.objects.get_or_create(
        id_sens=sensor_id,
        defaults={
            "station": station,
            "name": sensor_name,
            "type": sensor_type,
            "unit": unit,
            "freq": freq,
            "last_value": None,
            "last_timestamp": None,
        },
    )
    return sensor


def _normalize_sensor_name(name):
    return str(name).strip().replace(" ", "_")


def handle_station_payload(payload: dict):
    station_id = payload.get("station_id") or payload.get("st_id") or payload.get("src")
    if station_id is None:
        return

    station = _get_or_create_station(station_id)
    ts = _parse_timestamp(payload.get("timestamp"))

        # GPS direct
    if "latitude" in payload and "longitude" in payload:
        try:
            station.latitude = float(payload["latitude"])
            station.longitude = float(payload["longitude"])
            station.last_position = f"{station.latitude}, {station.longitude}"
        except Exception:
            pass

    # GPS dans un bloc "gps"
    if "gps" in payload and isinstance(payload["gps"], dict):
        lat = payload["gps"].get("lat")
        lon = payload["gps"].get("lon")

        if lat is not None and lon is not None:
            try:
                station.latitude = float(lat)
                station.longitude = float(lon)
                station.last_position = f"{station.latitude}, {station.longitude}"
            except Exception:
                pass

    station.last_timestamp = ts
    station.is_Wifi = True
    station.is_Lora = True
    station.save()

    reserved_keys = {
        "station_id",
        "st_id",
        "src",
        "timestamp",
        "t",
        "seq",
        "mid",
        "hop",
        "ttl",
        "dst",
        "crc",
    }

    unit_map = {
        "temperature": "°C",
        "humidity": "%",
        "pressure": "hPa",
        "temp_c": "°C",
        "hu_p": "%",
        "pr_hpa": "hPa",
    }

    # Cas 1 : JSON simple
    for key, value in payload.items():
        if key in reserved_keys:
            continue

        if isinstance(value, dict):
            continue

        if not isinstance(value, (int, float)):
            continue

        clean_key = _normalize_sensor_name(key)

        sensor = _get_or_create_sensor(
            station=station,
            sensor_name=clean_key,
            unit=unit_map.get(clean_key, ""),
            sensor_type=clean_key,
            freq=0,
        )

        sensor.last_value = float(value)
        sensor.last_timestamp = ts
        sensor.save()

        Data.objects.create(
            station=station,
            sensor=sensor,
            timestamp=ts,
            value=float(value),
        )

    # Cas 2 : JSON STM32 avec bloc ss
    if "ss" in payload and isinstance(payload["ss"], dict):
        for key, value in payload["ss"].items():
            if not isinstance(value, (int, float)):
                continue

            clean_key = _normalize_sensor_name(key)

            sensor = _get_or_create_sensor(
                station=station,
                sensor_name=clean_key,
                unit=unit_map.get(clean_key, ""),
                sensor_type=clean_key,
                freq=0,
            )

            sensor.last_value = float(value)
            sensor.last_timestamp = ts
            sensor.save()

            Data.objects.create(
                station=station,
                sensor=sensor,
                timestamp=ts,
                value=float(value),
            )


def on_connect(client, userdata, flags, reason_code, properties=None):
    print("MQTT connected with reason code:", reason_code)
    client.subscribe("envirosense/station/+/data")
    client.subscribe("envirosense/station/+/ack")
    client.subscribe("envirosense/station/+/status")


def on_message(client, userdata, msg):
    topic = msg.topic
    raw = msg.payload.decode("utf-8", errors="ignore")

    print("MQTT message:", topic, raw)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print("JSON invalide, message ignore.")
        return

    if topic.endswith("/data"):
        handle_station_payload(payload)


def create_mqtt_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    if settings.MQTT_USERNAME:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message

    return client


def run_forever():
    client = create_mqtt_client()
    client.connect(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, 60)
    client.loop_forever()


def publish_station_command(station_id, command, value):
    client = create_mqtt_client()
    client.connect(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, 60)

    topic = f"envirosense/station/{station_id}/cmd"
    payload = json.dumps({
        "cmd": command,
        "value": value,
    })

    client.loop_start()
    client.publish(topic, payload)
    client.loop_stop()
    client.disconnect()