"""Envoi des courriels du portail EnviroSense.

Les courriels partent de DEFAULT_FROM_EMAIL
(noreplyenvirosense@usherbrooke.ca) par le serveur SMTP regle dans
settings.py (smtp.usherbrooke.ca, port 25, sans authentification).
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def site_url(request):
    """Adresse de base du site pour les liens des courriels."""
    site = getattr(settings, "SITE_URL", "")
    if site:
        return site.rstrip("/")
    return request.build_absolute_uri("/").rstrip("/")


def envoyer_courriel(sujet, destinataire, gabarit, contexte):
    """Envoie un courriel texte + HTML a partir de
    templates/emails/<gabarit>.txt et .html.

    Retourne True si le serveur SMTP a accepte le message, False sinon.
    Une erreur d'envoi ne fait jamais planter la page : elle est
    seulement ecrite dans les logs du serveur.
    """
    texte = render_to_string(f"emails/{gabarit}.txt", contexte)
    html = render_to_string(f"emails/{gabarit}.html", contexte)

    message = EmailMultiAlternatives(
        subject=sujet,
        body=texte,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[destinataire],
    )
    message.attach_alternative(html, "text/html")

    try:
        message.send()
    except Exception:
        logger.exception(
            "Echec de l'envoi du courriel '%s' a %s (serveur %s:%s)",
            sujet, destinataire, settings.EMAIL_HOST, settings.EMAIL_PORT,
        )
        return False

    logger.info("Courriel '%s' envoye a %s", sujet, destinataire)
    return True


def envoyer_courriel_bienvenue(request, user):
    """Notification envoyee a la creation d'un compte."""
    base = site_url(request)
    contexte = {
        "email": user.email,
        "login_url": base + reverse("login"),
        "reset_url": base + reverse("password_reset"),
    }
    return envoyer_courriel(
        "Bienvenue sur EnviroSense : votre compte est créé",
        user.email,
        "bienvenue",
        contexte,
    )
