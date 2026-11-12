import json
import time
from datetime import datetime, timedelta, timezone as dt_timezone

import paho.mqtt.client as mqtt
from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone

from .models import Station, Sensor, Data, MeasurementBatch, StationCommand


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

# ============================================================
# FORMAT LIAISON -> ESP32 -> MQTT
#
# {"station_id":11,"src":11,"seq":3,"mid":12,"hop":0,
#  "rssi":-45,"snr":9,"csv":"<35 champs>"}
# ============================================================

CSV_COLUMNS = [
    "tick_ms", "dropped", "valid", "utc_iso", "fix_ok", "sats", "pdop",
    "lat", "lon", "alt_m", "speed_kmh", "gps_pvt",
    "pm1_0", "pm2_5", "pm4_0", "pm10",
    "nc_0p5", "nc_1p0", "nc_2p5", "nc_4p0", "nc_10p0",
    "temp_c", "humidity_rh", "x_g", "y_g", "z_g",
    "no2_na", "ox_na", "no2_ppm", "o3_ppm",
    "no2we_mv", "no2ae_mv", "o3we_mv", "o3ae_mv", "batt_mv",
]

# Colonnes CSV affichees comme capteurs dans le portail :
# colonne CSV -> (nom du capteur dans le portail, unite)
# "temperature" et "humidity" reprennent les icones deja prevues
# dans station_detail.html.
CSV_DISPLAYED_SENSORS = {
    "temp_c": ("temperature", "°C"),
    "humidity_rh": ("humidity", "%"),
    "pm1_0": ("pm1_0", "µg/m³"),
    "pm2_5": ("pm2_5", "µg/m³"),
    "pm4_0": ("pm4_0", "µg/m³"),
    "pm10": ("pm10", "µg/m³"),
    "no2_ppm": ("no2_ppm", "ppm"),
    "o3_ppm": ("o3_ppm", "ppm"),
    "batt_mv": ("batterie", "mV"),
}


def _csv_value(raw):
    raw = raw.strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return raw


def _parse_gps_utc(utc_iso, now):
    """utc_iso vient du GPS : heure UTC sans fuseau. Si absente ou
    incoherente (GPS pas encore synchronise), on garde l'heure de reception."""
    if not utc_iso or not isinstance(utc_iso, str):
        return now
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", ""))
    except ValueError:
        return now
    if timezone.is_naive(dt):
        dt = dt.replace(tzinfo=dt_timezone.utc)
    if abs(dt - now) > timedelta(days=1):
        return now
    return dt


def _parse_recu(value):
    """Heure (UTC) a laquelle l'ESP32 a recu la mesure ("recu" dans le JSON).
    Les mesures sont gardees par l'ESP32 et envoyees a 6 h et 18 h : c'est
    cette heure-la qui date la mesure, pas l'arrivee du lot."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(dt):
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt


def _update_gateway(topic, now):
    """La passerelle (station de liaison) est l'ID dans le topic MQTT."""
    parts = topic.split("/")
    if len(parts) < 3:
        return
    gateway, _ = Station.objects.get_or_create(
        id_stat=parts[2],
        defaults={"role": "liaison", "last_position": "---", "artefacts": ""},
    )
    gateway.last_timestamp = now
    gateway.is_Wifi = True
    gateway.is_Lora = True
    gateway.save(update_fields=["last_timestamp", "is_Wifi", "is_Lora"])


def handle_csv_payload(payload, topic=""):
    values = str(payload.get("csv", "")).split(",")
    # Aucune condition sur le nombre de champs : on enregistre ce qui arrive.
    # Champs manquants -> absents (None) ; champs en trop -> extra_1, extra_2...
    if len(values) != len(CSV_COLUMNS):
        print(f"[MQTT] Info : {len(values)} champs recus ({len(CSV_COLUMNS)} attendus), enregistre quand meme")

    station_id = payload.get("station_id") or payload.get("src")
    if station_id is None:
        print("[MQTT] CSV rejete : station_id manquant")
        return False

    measurements = {col: _csv_value(v) for col, v in zip(CSV_COLUMNS, values)}
    for i, v in enumerate(values[len(CSV_COLUMNS):], start=1):
        measurements[f"extra_{i}"] = _csv_value(v)
    for key in ("rssi", "snr", "hop", "seq"):
        if key in payload:
            measurements[f"lora_{key}"] = payload[key]

    now = timezone.now()
    recu = _parse_recu(payload.get("recu"))
    if recu is not None and recu > now + timedelta(minutes=5):
        recu = None   # horloge de l'ESP32 incoherente
    # Moment de la mesure : heure GPS, sinon heure de reception par l'ESP32,
    # sinon heure d'arrivee au serveur.
    vue_a = recu or now
    ts = _parse_gps_utc(measurements.get("utc_iso"), vue_a)
    # Anti-doublon : meme mesure recue 2 fois (relais LoRa, ou lot renvoye
    # par l'ESP32 apres une coupure). Le "mid" repart a 1 quand les cartes
    # redemarrent, donc on compare seulement avec les mesures datees a
    # +/- 2 minutes, ou arrivees dans les 2 dernieres minutes.
    key = (
        f"{payload.get('src', station_id)}-{payload.get('mid', '')}-"
        f"{measurements.get('tick_ms') or ''}-{measurements.get('utc_iso') or ''}"
    )
    message_id = f"{key}@{vue_a.strftime('%Y%m%dT%H%M%S.%f')}"

    with transaction.atomic():
        if topic:
            _update_gateway(topic, now)

        station = _get_or_create_station(station_id)

        if MeasurementBatch.objects.filter(
            Q(received_at__gte=now - timedelta(minutes=2))
            | Q(timestamp__range=(ts - timedelta(minutes=2), ts + timedelta(minutes=2))),
            station=station,
            message_id__startswith=f"{key}@",
        ).exists():
            # la station est bien vivante : on met quand meme a jour son statut
            if station.last_timestamp is None or vue_a > station.last_timestamp:
                station.last_timestamp = vue_a
                station.save(update_fields=["last_timestamp"])
            print(f"[MQTT] Doublon ignore : {key}")
            return True

        MeasurementBatch.objects.create(
            station=station,
            message_id=message_id,
            timestamp=ts,
            measurements=measurements,
        )

        # Statut "en ligne" = derniere mesure recue par l'ESP32
        if station.last_timestamp is None or vue_a > station.last_timestamp:
            station.last_timestamp = vue_a
        station.is_Lora = True

        lat, lon = measurements.get("lat"), measurements.get("lon")
        if isinstance(lat, float) and isinstance(lon, float) and (lat, lon) != (0.0, 0.0):
            station.latitude = lat
            station.longitude = lon
            station.last_position = f"{lat}, {lon}"
        station.save()

        saved = 0
        for col, (sensor_name, unit) in CSV_DISPLAYED_SENSORS.items():
            value = measurements.get(col)
            if not isinstance(value, float):
                continue
            sensor = _get_or_create_sensor(
                station=station,
                sensor_name=sensor_name,
                unit=unit,
                sensor_type=col,
                freq=0,
            )
            # derniere valeur = la plus recente (un lot renvoye peut etre plus vieux)
            if sensor.last_timestamp is None or ts >= sensor.last_timestamp:
                sensor.last_value = value
                sensor.last_timestamp = ts
                sensor.save(update_fields=["last_value", "last_timestamp"])
            Data.objects.create(station=station, sensor=sensor, timestamp=ts, value=value)
            saved += 1

    print(f"[MQTT] Station {station_id} : {saved} mesures enregistrees ({message_id})")
    return True


def save_measurement_batch(payload):
    measurements = payload.get("measurements")

    if not isinstance(measurements, dict):
        return False

    station_id = payload.get("station_id") or payload.get("st_id") or payload.get("src")

    if station_id is None:
        print("[MQTT] Erreur : station_id manquant")
        return False

    station = _get_or_create_station(station_id)

    timestamp = _parse_timestamp(
        payload.get("timestamp") or measurements.get("utc_iso")
    )

    # Identifiant unique pour éviter les doublons
    message_id = payload.get("message_id")

    if not message_id:
        tick_ms = measurements.get("tick_ms")

        if tick_ms is None:
            print("[MQTT] Erreur : message_id et tick_ms manquants")
            return False

        message_id = f"CSV-{station_id}-{timestamp.isoformat()}-{tick_ms}"

    # Convertir les champs vides en valeurs nulles
    cleaned_measurements = {
        key: None if value == "" else value
        for key, value in measurements.items()
    }

    batch, created = MeasurementBatch.objects.get_or_create(
        station=station,
        message_id=str(message_id),
        defaults={
            "timestamp": timestamp,
            "measurements": cleaned_measurements,
        },
    )

    if created:
        print(
            f"[MQTT] MeasurementBatch enregistré : "
            f"station={station_id}, "
            f"colonnes={len(cleaned_measurements)}, "
            f"message_id={message_id}"
        )
    else:
        print(f"[MQTT] Message déjà enregistré : {message_id}")

    return True

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

    if not isinstance(payload, dict):
        print("JSON qui n'est pas un objet, message ignore.")
        return

    # Processus de longue duree : evite une connexion PostgreSQL perimee
    close_old_connections()

    try:
        if topic.endswith("/ack"):
            handle_ack(payload, topic)
        elif topic.endswith("/data"):
            if "csv" in payload:
                # Format de la station de liaison (STM32 -> ESP32)
                handle_csv_payload(payload, topic)
            elif not save_measurement_batch(payload):
                handle_station_payload(payload)
        elif topic.endswith("/status"):
            _update_gateway(topic, timezone.now())
    except Exception as exc:
        # Un message invalide ne doit pas arreter le client MQTT
        print(f"[MQTT] Erreur traitement message : {exc!r}")


def create_mqtt_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    if settings.MQTT_USERNAME:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

    client.on_connect = on_connect
    client.on_message = on_message

    return client


def run_forever():
    client = create_mqtt_client()
    # Le broker peut demarrer apres Django (docker compose) : on reessaie
    while True:
        try:
            print(f"Connexion au broker {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}...")
            client.connect(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, 60)
            break
        except OSError as exc:
            print(f"Broker injoignable ({exc}), nouvel essai dans 3 s")
            time.sleep(3)
    client.loop_forever(retry_first_connection=False)


def publish_station_command(station_id, command, value):
    """Publie une commande pour une station. Retourne True si le broker l'a recue."""
    topic = f"envirosense/station/{station_id}/cmd"
    # JSON compact, sans espaces : l'ESP32 cherche exactement "cmd":"set_interval"
    payload = json.dumps({
        "cmd": command,
        "value": value,
    }, separators=(",", ":"))
    try:
        client = create_mqtt_client()
        client.connect(settings.MQTT_BROKER_HOST, settings.MQTT_BROKER_PORT, 60)
        client.loop_start()
        info = client.publish(topic, payload, qos=1)
        info.wait_for_publish(timeout=5)
        ok = info.is_published()
        client.loop_stop()
        client.disconnect()
        print(f"[MQTT] Commande publiee sur {topic} : {payload} (ok={ok})")
        return ok
    except Exception as exc:
        print(f"[MQTT] Echec publication commande : {exc!r}")
        return False


def handle_ack(payload, topic=""):
    """Suivi d'une commande set_interval :
    - {"result":"sent_to_stm32", "station_id":11, "value":30}  -> l'ESP32 l'a passee a la liaison
    - {"type":"ack", "station_id":11, "value":30, "ok":1}      -> la collecte l'a appliquee (ok=0 : refusee)
    """
    station_id = payload.get("station_id")
    value = payload.get("value")
    if station_id is None or value is None:
        return
    station_id = str(station_id)
    value = str(int(value))

    if payload.get("type") == "ack":
        new_status = "appliquee" if int(payload.get("ok", 0)) == 1 else "refusee"
    elif payload.get("result") == "sent_to_stm32":
        new_status = "transmise"
    else:
        return

    station = Station.objects.filter(id_stat=station_id).first()
    if station is None:
        print(f"[MQTT] Confirmation pour une station inconnue : {station_id}")
        return

    cmd = (
        StationCommand.objects
        .filter(station=station, command="set_interval", value=value)
        .order_by("-created_at")
        .first()
    )
    if cmd is None:
        # ex. diffusion a toutes les collectes depuis la station de liaison
        cmd = StationCommand(station=station, command="set_interval", value=value)
    # ne pas revenir en arriere (une confirmation peut arriver avant "transmise")
    if cmd.status in ("appliquee", "refusee") and new_status == "transmise":
        return
    cmd.status = new_status
    cmd.save()

    if new_status == "appliquee":
        Sensor.objects.filter(station=station).update(freq=float(value))

    print(f"[MQTT] Commande station {station_id} : {value} s -> {new_status}")