from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views

from . import views
from .forms import (
    EmailAuthenticationForm,
    EnvirosensePasswordResetForm,
    EnvirosenseSetPasswordForm,
)


urlpatterns = [
    path("", views.home, name="home"),
    path("home/", views.home, name="home"),

    path(
        "login/",
        auth_views.LoginView.as_view(
            authentication_form=EmailAuthenticationForm
        ),
        name="login"
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(next_page="login"),
        name="logout"
    ),

    path("signup/", views.signup, name="signup"),

    # --------------------------------------------------------
    # Mot de passe oublie (lien envoye par courriel)
    # --------------------------------------------------------
    path(
        "mot-de-passe/oublie/",
        auth_views.PasswordResetView.as_view(
            form_class=EnvirosensePasswordResetForm,
            template_name="registration/password_reset_form.html",
            subject_template_name="registration/password_reset_subject.txt",
            email_template_name="registration/password_reset_email.txt",
            html_email_template_name="registration/password_reset_email.html",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset"
    ),

    path(
        "mot-de-passe/oublie/envoye/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html",
        ),
        name="password_reset_done"
    ),

    path(
        "mot-de-passe/reinitialiser/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            form_class=EnvirosenseSetPasswordForm,
            template_name="registration/password_reset_confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm"
    ),

    path(
        "mot-de-passe/reinitialiser/termine/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html",
        ),
        name="password_reset_complete"
    ),

    path(
        "stations/<str:station_id>/",
        views.station_detail,
        name="station_detail"
    ),

    path(
        "stations/<str:station_id>/set-interval/",
        views.set_interval,
        name="set_interval"
    ),

    path(
        "stations/<str:station_id>/export-csv/",
        views.export_station_csv,
        name="export_station_csv"
    ),
]