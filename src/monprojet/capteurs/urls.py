from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('home/', views.home, name='home'),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path("signup/", views.signup, name="signup"),

    path("stations/<str:station_id>/", views.station_detail, name="station_detail"),
    path("stations/<str:station_id>/set-interval/", views.set_interval, name="set_interval"),
    path("stations/<str:station_id>/export-csv/", views.export_station_csv, name="export_station_csv"),
]