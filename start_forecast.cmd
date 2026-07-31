@echo off
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 goto USE_PY

where python >nul 2>nul
if not errorlevel 1 goto USE_PYTHON

echo Python was not found.
echo Install Python 3.11 or later and try again.
pause
exit /b 1

:USE_PY
py -3 launcher.py
goto FINISH

:USE_PYTHON
python launcher.py

:FINISH
if errorlevel 1 pause
