@echo off
chcp 65001 > nul
title Matraslar - Print Agent (iPOS MA-0780B)
echo ======================================================
echo    🖨 Запуск агента печати этикеток для Matraslar
echo ======================================================
echo.

cd /d "%~dp0"
python -m pip install pywin32 pillow --quiet

python print_agent.py

echo.
echo Агент печати остановлен.
pause
