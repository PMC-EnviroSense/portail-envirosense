from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User


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