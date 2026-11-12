@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo  TEST DES COURRIELS (inscription + mot de passe oublie)
echo ============================================================
echo.
echo [1/2] Tests automatiques (aucun vrai courriel envoye)...
docker compose up -d --build
if errorlevel 1 goto erreur_docker
timeout /t 10 /nobreak >nul
docker compose exec -T web python manage.py test capteurs -v 2
if errorlevel 1 goto erreur
echo.
echo ------------------------------------------------------------
echo [2/2] Envoi d'un VRAI courriel par smtp.usherbrooke.ca
echo       (le PC doit etre sur le reseau de l'UdeS ou son VPN)
echo ------------------------------------------------------------
set /p ADRESSE="Ton adresse courriel (Entree pour passer) : "
if "%ADRESSE%"=="" goto fin
docker compose exec -T web python manage.py sendtestemail %ADRESSE%
if errorlevel 1 goto erreur_smtp
echo Courriel envoye a %ADRESSE% par noreplyenvirosense@usherbrooke.ca.
echo Regarde aussi dans les indesirables.

:fin
echo.
echo ============================================================
echo  SUCCES
echo ============================================================
pause
exit /b 0

:erreur_docker
echo.
echo ECHEC : Docker ne repond pas. Ouvre Docker Desktop et attends
echo "Engine running", puis relance ce fichier.
pause
exit /b 1

:erreur_smtp
echo.
echo ECHEC : smtp.usherbrooke.ca n'a pas accepte le courriel.
echo  - Le PC est-il sur le reseau de l'UdeS (ou connecte au VPN) ?
echo    Le port 25 est souvent bloque par les fournisseurs Internet
echo    et le serveur sans authentification n'accepte que le reseau UdeS.
pause
exit /b 1

:erreur
echo.
echo ECHEC : voir les messages ci-dessus.
pause
exit /b 1
