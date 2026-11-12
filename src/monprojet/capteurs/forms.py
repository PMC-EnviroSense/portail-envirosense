from django import forms
import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.contrib.auth.models import User

logger = logging.getLogger("capteurs.emails")


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "placeholder": "Adresse courriel",
            "class": "form-input",
            "autocomplete": "email",
        })
    )

    class Meta:
        model = User
        fields = ("email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["email"].label = ""
        self.fields["password1"].label = ""
        self.fields["password2"].label = ""

        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

        self.fields["password1"].widget.attrs.update({
            "placeholder": "Mot de passe",
            "class": "form-input",
            "autocomplete": "new-password",
        })

        self.fields["password2"].widget.attrs.update({
            "placeholder": "Confirmer le mot de passe",
            "class": "form-input",
            "autocomplete": "new-password",
        })

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Un compte avec cette adresse courriel existe déjà."
            )

        return email

    def save(self, commit=True):
        user = super().save(commit=False)

        email = self.cleaned_data["email"].strip().lower()

        user.username = email
        user.email = email

        if commit:
            user.save()

        return user


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="",
        widget=forms.EmailInput(attrs={
            "placeholder": "Adresse courriel",
            "class": "form-input",
            "autocomplete": "email",
            "autofocus": True,
        })
    )

    password = forms.CharField(
        label="",
        strip=False,
        widget=forms.PasswordInput(attrs={
            "placeholder": "Mot de passe",
            "class": "form-input",
            "autocomplete": "current-password",
        })
    )


# ============================================================
# REINITIALISATION DU MOT DE PASSE
# ============================================================

class EnvirosensePasswordResetForm(PasswordResetForm):
    """Demande d'un lien de reinitialisation par courriel."""

    email = forms.EmailField(
        label="",
        max_length=254,
        widget=forms.EmailInput(attrs={
            "placeholder": "Adresse courriel du compte",
            "class": "form-input",
            "autocomplete": "email",
            "autofocus": True,
        })
    )

    def save(self, domain_override=None, use_https=False, **kwargs):
        # Si SITE_URL est regle dans .env, les liens du courriel l'utilisent
        # (sinon : l'adresse tapee dans le navigateur).
        site = getattr(settings, "SITE_URL", "")
        if site and not domain_override:
            url = urlsplit(site)
            domain_override = url.netloc
            use_https = url.scheme == "https"
        return super().save(
            domain_override=domain_override, use_https=use_https, **kwargs
        )

    def send_mail(self, *args, **kwargs):
        # Si le serveur SMTP ne repond pas, on l'ecrit dans les logs au
        # lieu d'afficher une erreur 500. La page affiche le meme message
        # dans tous les cas, pour ne pas reveler quelles adresses ont un
        # compte.
        destinataire = args[4] if len(args) > 4 else kwargs.get("to_email")
        try:
            super().send_mail(*args, **kwargs)
        except Exception:
            logger.exception(
                "Echec de l'envoi du courriel de reinitialisation a %s",
                destinataire,
            )


class EnvirosenseSetPasswordForm(SetPasswordForm):
    """Choix du nouveau mot de passe (lien recu par courriel)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["new_password1"].label = ""
        self.fields["new_password2"].label = ""
        self.fields["new_password1"].help_text = ""
        self.fields["new_password2"].help_text = ""

        self.fields["new_password1"].widget.attrs.update({
            "placeholder": "Nouveau mot de passe",
            "class": "form-input",
            "autocomplete": "new-password",
            "autofocus": True,
        })
        self.fields["new_password2"].widget.attrs.update({
            "placeholder": "Confirmer le nouveau mot de passe",
            "class": "form-input",
            "autocomplete": "new-password",
        })
