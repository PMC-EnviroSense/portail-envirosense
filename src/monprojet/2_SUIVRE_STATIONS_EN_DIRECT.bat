@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Affichage en direct de ce que la base recoit (Ctrl+C pour arreter).
echo Utilise-le pendant le test avec le materiel (ESP32 + STM32).
docker compose exec web python manage.py etat_stations --suivre
pause
