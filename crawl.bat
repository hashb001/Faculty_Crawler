@echo off
rem Runs the faculty crawler with its own Python environment.
rem Use it from any terminal as:  crawl  [URL or saved .html file]  [-o name.csv]
rem or double-click it. Results are saved in this folder.
setlocal
set "HERE=%~dp0"
if not exist "%HERE%.venv\Scripts\python.exe" (
    echo The crawler is not set up yet. Double-click setup.bat first.
    pause
    exit /b 1
)
pushd "%HERE%"
"%HERE%.venv\Scripts\python.exe" "%HERE%faculty_crawler.py" %*
set "CODE=%ERRORLEVEL%"
popd
echo.
echo Results are saved in: %HERE%
rem Keep the window open when started by double-click (the command line then names this file).
setlocal EnableDelayedExpansion
set "CL=!CMDCMDLINE!"
if /i not "!CL:%~nx0=!"=="!CL!" pause
exit /b %CODE%
