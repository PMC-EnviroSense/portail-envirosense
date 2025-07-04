# monprojet/Dockerfile

# Utilise une image officielle Python
FROM python:3.11-slim

# Désactive la mise en cache de fichiers .pyc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Crée un dossier de travail dans le conteneur
WORKDIR /app

# Copie et installe les dépendances Python
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copie tout le code dans le conteneur
COPY . /app/

# Démarre le serveur Django sur le port 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
