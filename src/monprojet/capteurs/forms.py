from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "placeholder": "Email",
            "class": "form-input"
        })
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
        widgets = {
            "username": forms.TextInput(attrs={
                "placeholder": "Nom d'utilisateur",
                "class": "form-input"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["username"].label = ""
        self.fields["email"].label = ""
        self.fields["password1"].label = ""
        self.fields["password2"].label = ""

        self.fields["password1"].help_text = ""
        self.fields["password2"].help_text = ""

        self.fields["password1"].widget.attrs.update({
            "placeholder": "Mot de passe",
            "class": "form-input"
        })
        self.fields["password2"].widget.attrs.update({
            "placeholder": "Confirmer le mot de passe",
            "class": "form-input"
        })

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte avec cet email existe déjà.")
        return email