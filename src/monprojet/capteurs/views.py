from datetime import datetime, time as dtime, timedelta

import csv

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from .emails import envoyer_courriel_bienvenue
from .forms import SignUpForm
from .models import Data, Sensor, Station, StationCommand
from .mqtt_client import publish_station_command


# Bornes acceptees par le firmware des collectes (MESH_TX_PERIOD_MIN/MAX_MS)
INTERVAL_MIN_S = 5
INTERVAL_MAX_S = 3600

COMMAND_STATUS_LABELS = {
    "sent": "Envoyée au serveur MQTT, en attente de la passerelle",
    "transmise": "Transmise à la station de liaison, en attente de la collecte",
    "appliquee": "Appliquée par la station",
    "refusee": "Refusée par la station",
    "echec_envoi": "Échec : serveur MQTT injoignable",
}


def _current_interval(station):
    """Derniere periode confirmee par la station (en secondes), ou None."""
    cmd = (
        StationCommand.objects
        .filter(station=station, command="set_interval", status="appliquee")
        .order_by("-created_at")
        .first()
    )
    return int(cmd.value) if cmd and str(cmd.value).isdigit() else None


def _offline_threshold(station):
    """Hors ligne si aucun message pendant 60 s, ou plus si la periode
    d'envoi de la station est longue (2 periodes + 20 s de marge)."""
    interval = _current_interval(station)
    seconds = 60
    if interval:
        seconds = max(seconds, 2 * interval + 20)
    return timedelta(seconds=seconds)


# ============================================================
# ENVOI DES MESURES 2 FOIS PAR JOUR (6 h et 18 h)
# L'ESP32 garde les mesures et les envoie toutes ensemble a ces heures
# (HEURES_ENVOI dans esp32_gateway/src/main.cpp : garder les memes).
# ============================================================

# Delai laisse a l'ESP32 pour envoyer le lot apres l'heure prevue
ENVOI_DELAI = timedelta(minutes=10)


def _heures_envoi():
    """Heures d'envoi des mesures ([] = envoi en temps reel)."""
    return sorted(set(getattr(settings, "ENVOI_HEURES", [6, 18]) or []))


def _creneaux_autour(now):
    """Heures d'envoi d'hier, d'aujourd'hui et de demain (heure locale)."""
    local = timezone.localtime(now)
    tz = timezone.get_current_timezone()
    creneaux = []
    for jours in (-1, 0, 1):
        jour = (local + timedelta(days=jours)).date()
        for h in _heures_envoi():
            creneaux.append(timezone.make_aware(datetime.combine(jour, dtime(h)), tz))
    return creneaux


def _dernier_envoi_prevu(now):
    """Dernier envoi qui devrait deja etre arrive (None = temps reel)."""
    passes = [c for c in _creneaux_autour(now) if c <= now - ENVOI_DELAI]
    return max(passes) if passes else None


def _prochain_envoi(now):
    futurs = [c for c in _creneaux_autour(now) if c > now]
    return min(futurs) if futurs else None


def _est_en_ligne(station, now):
    """Collectes : en ligne si elles ont mesure jusqu'au dernier envoi prevu
    (les mesures n'arrivent qu'a 6 h et 18 h).
    Liaison (ESP32) : signal de vie en temps reel, toutes les 20 s."""
    if not station.last_timestamp:
        return False
    marge = _offline_threshold(station)
    if station.role != "liaison":
        dernier = _dernier_envoi_prevu(now)
        if dernier is not None:
            return station.last_timestamp >= dernier - marge
    return now - station.last_timestamp <= marge


# ============================================================
# ACCUEIL / DASHBOARD
# ============================================================

@login_required
def home(request):
    stations = Station.objects.all().order_by("id_stat")

    rows = []
    map_stations = []

    offline_threshold = timedelta(seconds=60)
    now = timezone.now()

    online_count = 0
    offline_count = 0

    for station in stations:

        last_data = (
            Data.objects
            .filter(station=station)
            .order_by("-timestamp")
            .first()
        )

        sensor_count = (
            Sensor.objects
            .filter(station=station)
            .count()
        )

        is_online = _est_en_ligne(station, now)

        status = (
            "En ligne"
            if is_online
            else "Hors ligne"
        )

        if is_online:
            online_count += 1
        else:
            offline_count += 1

        rows.append({
            "station": station,
            "status": status,
            "is_online": is_online,
            "last_data": (
                last_data.timestamp
                if last_data
                else station.last_timestamp
            ),
            "sensor_count": sensor_count,
        })

        if (
            station.latitude is not None
            and station.longitude is not None
        ):
            map_stations.append({
                "id": station.id_stat,
                "lat": station.latitude,
                "lng": station.longitude,
                "status": status,
                "role": station.get_role_display(),
            })

    return render(
        request,
        "home.html",
        {
            "rows": rows,
            "map_stations": map_stations,
            "online_count": online_count,
            "offline_count": offline_count,
            "heures_envoi": _heures_envoi(),
            "prochain_envoi": _prochain_envoi(now),
        }
    )


# ============================================================
# DETAIL D'UNE STATION
# ============================================================

@login_required
def station_detail(request, station_id):

    station = get_object_or_404(
        Station,
        id_stat=station_id
    )

    sensors = (
        Sensor.objects
        .filter(station=station)
        .order_by("name")
    )

    data_rows = (
        Data.objects
        .filter(station=station)
        .select_related("sensor")
        .order_by("-timestamp")[:100]
    )

    # Même règle que le Dashboard :
    # plus de 60 secondes sans communication = hors ligne

    offline_threshold = timedelta(seconds=60)
    now = timezone.now()

    is_online = _est_en_ligne(station, now)

    last_command = (
        StationCommand.objects
        .filter(station=station, command="set_interval")
        .order_by("-created_at")
        .first()
    )

    return render(
        request,
        "station_detail.html",
        {
            "station": station,
            "sensors": sensors,
            "data_rows": data_rows,
            "is_online": is_online,
            "last_command": last_command,
            "last_command_label": (
                COMMAND_STATUS_LABELS.get(last_command.status, last_command.status)
                if last_command else ""
            ),
            "current_interval": _current_interval(station),
            "interval_min": INTERVAL_MIN_S,
            "interval_max": INTERVAL_MAX_S,
            # periode proposee par defaut pour le telechargement : dernieres 24 h
            "export_debut": timezone.localtime(now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M"),
            "export_fin": timezone.localtime(now).strftime("%Y-%m-%dT%H:%M"),
        }
    )


# ============================================================
# MODIFICATION DE LA FREQUENCE
# ============================================================

@login_required
@require_POST
def set_interval(request, station_id):

    station = get_object_or_404(
        Station,
        id_stat=station_id
    )

    interval = (
        request.POST
        .get("interval", "")
        .strip()
    )

    if not interval.isdigit() or not (INTERVAL_MIN_S <= int(interval) <= INTERVAL_MAX_S):
        messages.error(
            request,
            f"Période invalide : entre {INTERVAL_MIN_S} et {INTERVAL_MAX_S} secondes."
        )
        return redirect("station_detail", station_id=station_id)

    # Chemin : site -> MQTT -> ESP32 -> liaison (UART) -> collecte (LoRa).
    # La collecte confirme par le chemin inverse ; le statut est mis a jour
    # par le client MQTT (capteurs/mqtt_client.py, handle_ack).
    sent = publish_station_command(
        station_id,
        "set_interval",
        int(interval)
    )

    StationCommand.objects.create(
        station=station,
        command="set_interval",
        value=interval,
        status="sent" if sent else "echec_envoi",
    )

    if sent:
        messages.success(
            request,
            f"Demande envoyée : {interval} s. Confirmation de la station "
            f"dans quelques secondes (rafraîchis la page)."
        )
    else:
        messages.error(request, "Le serveur MQTT ne répond pas : demande non envoyée.")

    return redirect(
        "station_detail",
        station_id=station_id
    )


# ============================================================
# EXPORT CSV
# ============================================================

@login_required
def export_station_csv(request, station_id):
    """Export CSV des mesures d'une station sur une periode.

    Parametres GET (format des champs <input type="datetime-local">,
    heure locale) : ?debut=2026-10-28T08:00&fin=2026-10-28T17:00
    Sans parametre : tout l'historique.
    """
    station = get_object_or_404(
        Station,
        id_stat=station_id
    )

    debut_txt = request.GET.get("debut", "").strip()
    fin_txt = request.GET.get("fin", "").strip()

    try:
        debut = _parse_local_datetime(debut_txt)
        fin = _parse_local_datetime(fin_txt)
    except ValueError:
        messages.error(request, "Date invalide.", extra_tags="export")
        return redirect("station_detail", station_id=station_id)

    if debut and fin and debut > fin:
        messages.error(
            request,
            "La date de début doit être avant la date de fin.",
            extra_tags="export",
        )
        return redirect("station_detail", station_id=station_id)

    data_rows = (
        Data.objects
        .filter(station=station)
        .select_related("sensor")
    )
    if debut:
        data_rows = data_rows.filter(timestamp__gte=debut)
    if fin:
        # le champ est a la minute pres : on inclut toute la minute de fin
        data_rows = data_rows.filter(timestamp__lt=fin + timedelta(minutes=1))
    data_rows = data_rows.order_by("timestamp", "sensor__name")

    if not data_rows.exists():
        messages.error(
            request,
            "Aucune donnée pour cette station sur la période choisie.",
            extra_tags="export",
        )
        return redirect("station_detail", station_id=station_id)

    def _nom(dt):
        return timezone.localtime(dt).strftime("%Y-%m-%d_%Hh%M") if dt else "tout"

    if debut or fin:
        filename = f"station_{station_id}_{_nom(debut)}_au_{_nom(fin)}.csv"
    else:
        filename = f"station_{station_id}_historique_complet.csv"

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")  # BOM : accents et unites corrects dans Excel

    writer = csv.writer(response)
    writer.writerow(["date_heure_locale", "capteur", "valeur", "unite"])

    for row in data_rows.iterator():
        writer.writerow([
            timezone.localtime(row.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
            row.sensor.name,
            row.value,
            row.sensor.unit,
        ])

    return response


def _parse_local_datetime(txt):
    """'2026-10-28T08:00' (heure locale du site) -> datetime avec fuseau, ou None."""
    if not txt:
        return None
    dt = datetime.fromisoformat(txt)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


# ============================================================
# INSCRIPTION
# ============================================================

def signup(request):

    if request.method == "POST":

        form = SignUpForm(request.POST)

        if form.is_valid():

            user = form.save()

            clients_group, _ = (
                Group.objects
                .get_or_create(name="Clients")
            )

            user.groups.add(clients_group)

            login(request, user)

            # Notification de creation de compte (noreply EnviroSense).
            # Si l'envoi echoue, le compte est quand meme cree.
            if envoyer_courriel_bienvenue(request, user):
                messages.success(
                    request,
                    f"Compte créé. Un courriel de confirmation a été "
                    f"envoyé à {user.email}."
                )
            else:
                messages.warning(
                    request,
                    "Compte créé, mais le courriel de confirmation n'a "
                    "pas pu être envoyé."
                )

            return redirect("home")

    else:
        form = SignUpForm()

    return render(
        request,
        "signup.html",
        {
            "form": form
        }
    )