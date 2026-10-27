@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment not found: .venv\Scripts\python.exe
  echo Open the project README and complete the Windows setup first.
  pause
  exit /b 1
)
echo Installing optional test tools. The Chromium browser download is needed once.
".venv\Scripts\python.exe" -m pip install -r tests\measurements\requirements-local.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto failed
echo Running local measurements. This usually takes 5-10 minutes.
".venv\Scripts\python.exe" -X utf8 tests\measurements\run_local.py
if errorlevel 1 goto failed
echo Done. Results are in test-results. The HTML report opens in your browser.
pause
exit /b 0
:failed
echo A step failed. Keep this window open and copy the final error message.
pause
exit /b 1
