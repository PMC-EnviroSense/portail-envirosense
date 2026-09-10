from datetime import timedelta

import csv

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from .forms import SignUpForm
from .models import Data, Sensor, Station, StationCommand
from .mqtt_client import publish_station_command


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
        last_data = Data.objects.filter(station=station).order_by("-timestamp").first()
        sensor_count = Sensor.objects.filter(station=station).count()

        is_online = False
        if station.last_timestamp:
            is_online = (now - station.last_timestamp) <= offline_threshold

        status = "En ligne" if is_online else "Hors ligne"

        if is_online:
            online_count += 1
        else:
            offline_count += 1

        rows.append({
            "station": station,
            "status": status,
            "last_data": last_data.timestamp if last_data else None,
            "sensor_count": sensor_count,
        })

        if station.latitude is not None and station.longitude is not None:
            map_stations.append({
                "id": station.id_stat,
                "lat": station.latitude,
                "lng": station.longitude,
                "status": status,
            })

    return render(request, "home.html", {
        "rows": rows,
        "map_stations": map_stations,
        "online_count": online_count,
        "offline_count": offline_count,
    })


@login_required
def station_detail(request, station_id):
    station = get_object_or_404(Station, id_stat=station_id)
    sensors = Sensor.objects.filter(station=station).order_by("name")
    data_rows = Data.objects.filter(station=station).select_related("sensor").order_by("-timestamp")[:100]

    return render(request, "station_detail.html", {
        "station": station,
        "sensors": sensors,
        "data_rows": data_rows,
    })


@login_required
@require_POST
def set_interval(request, station_id):
    station = get_object_or_404(Station, id_stat=station_id)
    interval = request.POST.get("interval", "").strip()

    if interval.isdigit():
        publish_station_command(station_id, "set_interval", int(interval))
        StationCommand.objects.create(
            station=station,
            command="set_interval",
            value=interval,
            status="sent",
        )

        temp_sensor = Sensor.objects.filter(station=station, name="temperature").first()
        if temp_sensor:
            temp_sensor.freq = float(interval)
            temp_sensor.save()

    return redirect("station_detail", station_id=station_id)


@login_required
def export_station_csv(request, station_id):
    station = get_object_or_404(Station, id_stat=station_id)
    data_rows = Data.objects.filter(station=station).select_related("sensor").order_by("-timestamp")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="station_{station_id}_data.csv"'

    writer = csv.writer(response)
    writer.writerow(["timestamp", "sensor", "value"])

    for row in data_rows:
        writer.writerow([row.timestamp, row.sensor.name, row.value])

    return response


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            clients_group, _ = Group.objects.get_or_create(name="Clients")
            user.groups.add(clients_group)

            login(request, user)
            return redirect("home")
    else:
        form = SignUpForm()

    return render(request, "signup.html", {"form": form})