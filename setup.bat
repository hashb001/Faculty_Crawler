@echo off
rem One-time setup for the faculty crawler on Windows. Double-click this file.
setlocal
cd /d "%~dp0"
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (
    where python >nul 2>nul && python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY goto nopython

echo Creating the Python environment in "%HERE%\.venv" ...
%PY% -m venv .venv || goto fail
echo Installing the required package ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt || goto fail

echo.
choice /m "Add a 'crawl' command that works in any Command Prompt or PowerShell window"
if errorlevel 2 goto done
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d = $env:HERE; $p = [string][Environment]::GetEnvironmentVariable('Path', 'User'); if (($p -split ';') -notcontains $d) { [Environment]::SetEnvironmentVariable('Path', (($p.TrimEnd(';'), $d) -join ';').TrimStart(';'), 'User') }" || goto fail
echo Added. Close this window and open a NEW terminal for 'crawl' to work.

:done
echo.
echo Setup complete. To use it: double-click crawl.bat, or type  crawl  in a new terminal.
pause
exit /b 0

:nopython
echo Python was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH"
echo on the first screen of the installer, then double-click setup.bat again.
pause
exit /b 1

:fail
echo.
echo Setup failed. Read the message above, then try again.
pause
exit /b 1
