"""
Affiche l'etat de la chaine : ce que la base PostgreSQL a recu, par station.

  python manage.py etat_stations               -> un affichage
  python manage.py etat_stations --suivre      -> rafraichi toutes les 5 s (Ctrl+C pour arreter)
  python manage.py etat_stations --verifier 11 -> REUSSI si la station 11 a recu
                                                  une mesure dans les 2 dernieres minutes
"""
import sys
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from capteurs.models import Data, Sensor, Station


class Command(BaseCommand):
    help = "Etat des stations et des dernieres mesures recues"

    def add_arguments(self, parser):
        parser.add_argument("--suivre", action="store_true")
        parser.add_argument("--verifier", metavar="STATION_ID")

    def afficher(self):
        now = timezone.now()
        local = timezone.localtime(now).strftime("%H:%M:%S")
        print(f"\n===== Etat des stations ({local}) =====")
        stations = Station.objects.all().order_by("id_stat")
        if not stations:
            print("Aucune station en base pour le moment.")
        for st in stations:
            if st.last_timestamp:
                age = int((now - st.last_timestamp).total_seconds())
                etat = "EN LIGNE " if age <= 60 else "HORS LIGNE"
                vu = f"dernier message il y a {age} s"
            else:
                etat, vu = "JAMAIS VU", ""
            nb = Data.objects.filter(station=st).count()
            print(f"Station {st.id_stat:>4} [{st.role:8}] {etat} | {nb} mesures en base | {vu}")
            for s in Sensor.objects.filter(station=st).order_by("name"):
                if s.last_value is not None:
                    print(f"      {s.name:12} = {s.last_value:g} {s.unit}")

    def handle(self, *args, **opts):
        if opts["verifier"]:
            self.afficher()
            limite = timezone.now() - timedelta(minutes=2)
            ok = Data.objects.filter(
                station_id=opts["verifier"], timestamp__gte=limite
            ).exists() or Station.objects.filter(
                id_stat=opts["verifier"], last_timestamp__gte=limite
            ).exists()
            print()
            if ok:
                print(f"REUSSI : la station {opts['verifier']} a des mesures recentes en base.")
            else:
                print(f"ECHEC : aucune mesure recente pour la station {opts['verifier']}.")
                sys.exit(1)
            return

        if not opts["suivre"]:
            self.afficher()
            return

        try:
            while True:
                close_old_connections()
                self.afficher()
                time.sleep(5)
        except KeyboardInterrupt:
            pass
