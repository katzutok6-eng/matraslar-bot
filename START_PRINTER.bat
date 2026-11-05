@echo off
title Matraslar - Print Agent (iPOS MA-0780B)
cd /d "%~dp0"

echo ======================================================
echo    Matraslar - Print Agent (iPOS MA-0780B)
echo ======================================================
echo.

echo [*] Searching for Python...
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
    echo [ERROR] Python not found on this computer.
    echo Please install Python from https://www.python.org
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

echo [+] Using Python: %PY_CMD%
echo [*] Checking required libraries (pywin32)...
"%PY_CMD%" -m pip install pywin32 --quiet

echo [*] Starting Print Agent...
"%PY_CMD%" print_agent.py

echo.
echo Print Agent stopped.
pause
