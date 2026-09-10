from django.core.management.base import BaseCommand
from capteurs.mqtt_client import run_forever


class Command(BaseCommand):
    help = "Lance l'abonnement MQTT pour recevoir les donnees des stations"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Demarrage du client MQTT..."))
        run_forever()