"""Tests du compte utilisateur : courriel de bienvenue et mot de passe oublie.

Lancer : python manage.py test capteurs
(ou double-clic sur 4_TESTER_COURRIELS.bat)

Pendant les tests, Django n'envoie aucun vrai courriel : ils sont gardes
dans mail.outbox pour etre verifies.
"""

import re
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

EXPEDITEUR = "noreplyenvirosense@usherbrooke.ca"
MOT_DE_PASSE = "Capteur-Lora-2026"


class CourrielInscriptionTests(TestCase):

    def inscrire(self, email="etudiant@usherbrooke.ca"):
        return self.client.post(reverse("signup"), {
            "email": email,
            "password1": MOT_DE_PASSE,
            "password2": MOT_DE_PASSE,
        })

    def test_reglages_smtp(self):
        from django.conf import settings
        self.assertEqual(settings.EMAIL_HOST, "smtp.usherbrooke.ca")
        self.assertEqual(settings.EMAIL_PORT, 25)
        self.assertEqual(settings.EMAIL_HOST_USER, "")
        self.assertEqual(settings.EMAIL_HOST_PASSWORD, "")
        self.assertIn(EXPEDITEUR, settings.DEFAULT_FROM_EMAIL)

    def test_inscription_envoie_un_courriel(self):
        reponse = self.inscrire("Etudiant@USherbrooke.ca")

        self.assertRedirects(reponse, reverse("home"),
                             fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        courriel = mail.outbox[0]
        self.assertEqual(courriel.to, ["etudiant@usherbrooke.ca"])
        self.assertIn(EXPEDITEUR, courriel.from_email)
        self.assertIn("Bienvenue", courriel.subject)
        self.assertIn("etudiant@usherbrooke.ca", courriel.body)
        self.assertIn("http://testserver/login/", courriel.body)
        # version HTML jointe
        self.assertEqual(courriel.alternatives[0][1], "text/html")

        page = self.client.get(reverse("home"))
        self.assertContains(page, "Un courriel de confirmation a été envoyé")

    def test_inscription_refusee_aucun_courriel(self):
        User.objects.create_user("deja@usherbrooke.ca", "deja@usherbrooke.ca", "x")
        reponse = self.inscrire("deja@usherbrooke.ca")

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_serveur_smtp_injoignable_compte_quand_meme_cree(self):
        with mock.patch(
            "django.core.mail.EmailMultiAlternatives.send",
            side_effect=OSError("serveur injoignable"),
        ), self.assertLogs("capteurs.emails", level="ERROR"):
            reponse = self.inscrire()

        self.assertRedirects(reponse, reverse("home"),
                             fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(email="etudiant@usherbrooke.ca").exists())
        page = self.client.get(reverse("home"))
        self.assertContains(page, "n&#x27;a pas pu être envoyé")

    @override_settings(SITE_URL="https://envirosense.example.ca")
    def test_site_url_dans_le_courriel(self):
        self.inscrire()
        self.assertIn("https://envirosense.example.ca/login/", mail.outbox[0].body)


class MotDePasseOublieTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            "etudiant@usherbrooke.ca", "etudiant@usherbrooke.ca", "ancien-mdp-123"
        )

    def demander_lien(self, email):
        return self.client.post(reverse("password_reset"), {"email": email})

    def lien_du_courriel(self):
        trouve = re.search(r"http://testserver(/mot-de-passe/reinitialiser/\S+/)",
                           mail.outbox[0].body)
        self.assertIsNotNone(trouve, mail.outbox[0].body)
        return trouve.group(1)

    def test_lien_sur_la_page_de_connexion(self):
        page = self.client.get(reverse("login"))
        self.assertContains(page, reverse("password_reset"))
        self.assertContains(page, "Mot de passe oublié")

    def test_pages_s_affichent(self):
        for nom in ("password_reset", "password_reset_done", "password_reset_complete"):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 200, nom)

    def test_demande_envoie_le_lien(self):
        reponse = self.demander_lien("ETUDIANT@usherbrooke.ca")

        self.assertRedirects(reponse, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        courriel = mail.outbox[0]
        self.assertEqual(courriel.to, ["etudiant@usherbrooke.ca"])
        self.assertIn(EXPEDITEUR, courriel.from_email)
        self.assertIn("réinitialisation", courriel.subject)
        self.assertEqual(courriel.alternatives[0][1], "text/html")

    def test_adresse_inconnue_meme_page_sans_courriel(self):
        reponse = self.demander_lien("inconnu@usherbrooke.ca")

        self.assertRedirects(reponse, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_reinitialisation_complete(self):
        self.demander_lien("etudiant@usherbrooke.ca")
        lien = self.lien_du_courriel()

        # Django redirige le lien vers .../set-password/ (jeton cache en session)
        page = self.client.get(lien, follow=True)
        self.assertContains(page, "Nouveau mot de passe")
        formulaire_url = page.redirect_chain[-1][0]

        reponse = self.client.post(formulaire_url, {
            "new_password1": MOT_DE_PASSE,
            "new_password2": MOT_DE_PASSE,
        })
        self.assertRedirects(reponse, reverse("password_reset_complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(MOT_DE_PASSE))

        # le meme lien ne fonctionne plus
        page = self.client.get(lien, follow=True)
        self.assertContains(page, "Lien invalide")

        # connexion avec le nouveau mot de passe
        reponse = self.client.post(reverse("login"), {
            "username": "etudiant@usherbrooke.ca",
            "password": MOT_DE_PASSE,
        })
        self.assertRedirects(reponse, reverse("home"))

    def test_lien_falsifie(self):
        page = self.client.get(
            reverse("password_reset_confirm", args=["MQ", "faux-jeton"]))
        self.assertContains(page, "Lien invalide")

    def test_serveur_smtp_injoignable_pas_d_erreur_500(self):
        with mock.patch(
            "django.core.mail.EmailMultiAlternatives.send",
            side_effect=OSError("serveur injoignable"),
        ), self.assertLogs(level="ERROR"):
            reponse = self.demander_lien("etudiant@usherbrooke.ca")

        self.assertRedirects(reponse, reverse("password_reset_done"))

    @override_settings(SITE_URL="https://envirosense.example.ca")
    def test_site_url_dans_le_lien(self):
        self.demander_lien("etudiant@usherbrooke.ca")
        self.assertIn("https://envirosense.example.ca/mot-de-passe/reinitialiser/",
                      mail.outbox[0].body)


# ============================================================
# ENVOI DES MESURES 2 FOIS PAR JOUR (lot envoye par l'ESP32 a 6 h et 18 h)
# ============================================================

from datetime import datetime, timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from django.utils import timezone  # noqa: E402

from . import views  # noqa: E402
from .models import Data, MeasurementBatch, Station  # noqa: E402
from .mqtt_client import handle_csv_payload  # noqa: E402

QUEBEC = ZoneInfo("America/Montreal")
CSV_SANS_GPS = ("1000,0,7,,0,0,,,,,,,0.1,0.2,0.3,0.4,0.9,1.0,1.0,1.0,1.0,"
                "19.60,43.70,0.000,0.000,1.000,,,,,2499.7,2499.7,2499.8,2499.8,4290")


def mesure(tick, recu=None):
    payload = {"station_id": 11, "src": 11, "seq": tick, "mid": tick,
               "hop": 0, "rssi": -45, "snr": 9,
               "csv": CSV_SANS_GPS.replace("1000,", f"{tick},", 1)}
    if recu is not None:
        payload["recu"] = recu.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
    return payload


class EnvoiGroupeMqttTests(TestCase):

    def test_mesure_datee_a_sa_reception_par_l_esp32(self):
        recu = (timezone.now() - timedelta(hours=5)).replace(microsecond=0)
        handle_csv_payload(mesure(1000, recu), "envirosense/station/1/data")

        station = Station.objects.get(id_stat="11")
        self.assertEqual(station.last_timestamp, recu)
        temperature = Data.objects.get(station=station, sensor__name="temperature")
        self.assertEqual(temperature.timestamp, recu)
        self.assertEqual(temperature.value, 19.6)

    def test_lot_complet_dans_l_ordre(self):
        debut = (timezone.now() - timedelta(hours=12)).replace(microsecond=0)
        for i in range(30):   # 30 mesures, une toutes les 20 s
            handle_csv_payload(mesure(1000 + i * 20000, debut + timedelta(seconds=20 * i)),
                               "envirosense/station/1/data")

        self.assertEqual(MeasurementBatch.objects.count(), 30)
        station = Station.objects.get(id_stat="11")
        self.assertEqual(station.last_timestamp, debut + timedelta(seconds=20 * 29))

    def test_lot_renvoye_pas_de_doublon(self):
        debut = (timezone.now() - timedelta(hours=3)).replace(microsecond=0)
        lot = [mesure(1000 + i * 20000, debut + timedelta(seconds=20 * i)) for i in range(5)]
        for p in lot:
            handle_csv_payload(p, "envirosense/station/1/data")
        for p in lot:   # l'ESP32 renvoie le meme lot apres une coupure
            handle_csv_payload(p, "envirosense/station/1/data")

        self.assertEqual(MeasurementBatch.objects.count(), 5)
        self.assertEqual(Data.objects.filter(sensor__name="temperature").count(), 5)

    def test_sans_recu_heure_d_arrivee(self):
        avant = timezone.now()
        handle_csv_payload(mesure(1000), "envirosense/station/1/data")
        station = Station.objects.get(id_stat="11")
        self.assertGreaterEqual(station.last_timestamp, avant)


@override_settings(ENVOI_HEURES=[6, 18])
class EnvoiGroupeEtatTests(TestCase):

    def heure(self, jour, h, m=0):
        return datetime(2026, 11, jour, h, m, tzinfo=QUEBEC)

    def collecte(self, derniere_mesure):
        return Station.objects.create(id_stat="11", role="collecte",
                                      last_position="---", last_timestamp=derniere_mesure)

    def test_creneaux(self):
        now = self.heure(12, 11, 0)
        self.assertEqual(views._dernier_envoi_prevu(now), self.heure(12, 6))
        self.assertEqual(views._prochain_envoi(now), self.heure(12, 18))
        # juste apres 18 h : on laisse 10 min a l'ESP32 pour envoyer
        self.assertEqual(views._dernier_envoi_prevu(self.heure(12, 18, 5)), self.heure(12, 6))
        self.assertEqual(views._dernier_envoi_prevu(self.heure(12, 18, 15)), self.heure(12, 18))
        # la nuit : dernier envoi = 18 h la veille, prochain = 6 h
        self.assertEqual(views._dernier_envoi_prevu(self.heure(13, 2)), self.heure(12, 18))
        self.assertEqual(views._prochain_envoi(self.heure(13, 2)), self.heure(13, 6))

    def test_collecte_en_ligne_entre_deux_envois(self):
        # derniere mesure du lot de 18 h : 17:59:40 ; a 23 h il n'y a rien de plus
        station = self.collecte(self.heure(12, 17, 59) + timedelta(seconds=40))
        self.assertTrue(views._est_en_ligne(station, self.heure(12, 23)))
        self.assertTrue(views._est_en_ligne(station, self.heure(13, 6, 5)))

    def test_collecte_hors_ligne_si_mesures_arretees(self):
        # plus aucune mesure depuis 10 h : le lot de 18 h le montre
        station = self.collecte(self.heure(12, 10))
        self.assertTrue(views._est_en_ligne(station, self.heure(12, 17)))
        self.assertFalse(views._est_en_ligne(station, self.heure(12, 18, 15)))

    def test_liaison_reste_en_temps_reel(self):
        liaison = Station.objects.create(id_stat="1", role="liaison", last_position="---",
                                         last_timestamp=self.heure(12, 10))
        self.assertTrue(views._est_en_ligne(liaison, self.heure(12, 10, 0) + timedelta(seconds=30)))
        self.assertFalse(views._est_en_ligne(liaison, self.heure(12, 10, 5)))

    @override_settings(ENVOI_HEURES=[])
    def test_temps_reel_si_aucune_heure(self):
        station = self.collecte(self.heure(12, 10))
        self.assertIsNone(views._dernier_envoi_prevu(self.heure(12, 23)))
        self.assertFalse(views._est_en_ligne(station, self.heure(12, 10, 5)))

    def test_tableau_de_bord_affiche_les_heures(self):
        User.objects.create_user("a@usherbrooke.ca", "a@usherbrooke.ca", MOT_DE_PASSE)
        self.client.login(username="a@usherbrooke.ca", password=MOT_DE_PASSE)
        page = self.client.get(reverse("home"))
        self.assertContains(page, "Mesures envoyées au site à 6 h et 18 h")
