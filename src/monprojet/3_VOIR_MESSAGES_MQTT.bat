@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Messages MQTT recus par Django (Ctrl+C pour arreter)...
docker compose logs -f --tail 20 mqtt
pause
