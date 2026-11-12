from pathlib import Path
import os
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-dev-key")
DEBUG = os.getenv("DEBUG", "True") == "True"

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'capteurs.apps.CapteursConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'monsite.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'monsite.wsgi.application'

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr-ca'
TIME_ZONE = 'America/Montreal'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/home/"

MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "127.0.0.1")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

# ============================================================
# ENVOI DES MESURES : l'ESP32 envoie les mesures au site 2 fois par jour.
# Heures locales, separees par des virgules. Doivent etre les memes que
# HEURES_ENVOI dans esp32_gateway/src/main.cpp. Vide = temps reel.
# ============================================================
ENVOI_HEURES = [
    int(h) for h in os.getenv("ENVOI_HEURES", "6,18").split(",") if h.strip()
]

# ============================================================
# COURRIEL (serveur SMTP de l'Universite de Sherbrooke)
# smtp.usherbrooke.ca, port 25, sans authentification, sans TLS.
# Chaque valeur peut etre changee dans le fichier .env.
# Pour tester sans envoyer de vrai courriel (le message s'affiche
# dans la console du serveur) :
#   EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
# ============================================================
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.usherbrooke.ca")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "25"))
EMAIL_HOST_USER = ""        # sans authentification
EMAIL_HOST_PASSWORD = ""    # sans authentification
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "False") == "True"
EMAIL_USE_SSL = False
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))  # secondes

DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    "EnviroSense <noreplyenvirosense@usherbrooke.ca>",
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Duree de validite du lien de reinitialisation du mot de passe (24 h)
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

# Adresse du site a mettre dans les liens des courriels, par exemple
# SITE_URL=http://192.168.1.50:8000 . Vide = adresse utilisee par le
# navigateur au moment de la demande (ex. http://127.0.0.1:8000).
SITE_URL = os.getenv("SITE_URL", "").rstrip("/")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "capteurs.emails": {"handlers": ["console"], "level": "INFO"},
    },
}