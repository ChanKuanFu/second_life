@echo off
setlocal
taskkill /FI "WINDOWTITLE eq SecondLife API" /T /F
if errorlevel 1 echo No minimized SecondLife API window was found.
pause
