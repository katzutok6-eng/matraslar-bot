@echo off
chcp 65001 > nul
title Matraslar - Print Agent (iPOS MA-0780B)
echo ======================================================
echo    🖨 Запуск агента печати этикеток для Matraslar
echo ======================================================
echo.

cd /d "%~dp0"

:: Поиск установленного Python
set "PY_CMD="

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PY_CMD=python"
) else (
    where py >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        set "PY_CMD=py"
    ) else (
        for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*") do (
            if exist "%%D\python.exe" set "PY_CMD=%%D\python.exe"
        )
        if not defined PY_CMD (
            for /d %%D in ("%ProgramFiles%\Python*") do (
                if exist "%%D\python.exe" set "PY_CMD=%%D\python.exe"
            )
        )
    )
)

if not defined PY_CMD (
    echo [!] ОШИБКА: Python не найден на этом компьютере.
    echo Пожалуйста, установите Python с сайта https://www.python.org
    echo.
    pause
    exit /b 1
)

echo [+] Используется Python: %PY_CMD%
echo [*] Проверка библиотек (pywin32, pillow)...
%PY_CMD% -m pip install pywin32 pillow --quiet

echo [*] Запуск агента печати...
%PY_CMD% print_agent.py

echo.
echo Агент печати остановлен.
pause
