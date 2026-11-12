@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo  TEST AUTOMATIQUE DU SERVEUR (sans materiel)
echo  MQTT -^> Django -^> PostgreSQL -^> portail
echo ============================================================
echo.
echo [1/5] Construction et demarrage des conteneurs...
docker compose up -d --build
if errorlevel 1 goto erreur_docker
echo.
echo [2/5] Attente du demarrage (15 s)...
timeout /t 15 /nobreak >nul
docker compose ps
echo.
echo [3/5] Migrations de la base...
docker compose exec -T web python manage.py migrate --noinput
if errorlevel 1 goto erreur
echo.
echo [4/5] Envoi d'une fausse mesure MQTT (station 11)...
docker compose exec -T web python test_mqtt.py
if errorlevel 1 goto erreur
timeout /t 4 /nobreak >nul
echo.
echo [5/5] Verification dans PostgreSQL...
docker compose exec -T web python manage.py etat_stations --verifier 11
if errorlevel 1 goto erreur
echo.
echo ============================================================
echo  SUCCES : le serveur fonctionne.
echo  Ouvre http://127.0.0.1:8000 et clique sur la Station 11.
echo ============================================================
pause
exit /b 0

:erreur_docker
echo.
echo ECHEC : Docker ne repond pas. Ouvre Docker Desktop et attends
echo "Engine running", puis relance ce fichier.
pause
exit /b 1

:erreur
echo.
echo ============================================================
echo  ECHEC. Derniers messages du client MQTT :
echo ============================================================
docker compose logs --tail 40 mqtt
pause
exit /b 1
