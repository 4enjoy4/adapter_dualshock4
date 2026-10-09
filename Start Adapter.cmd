@echo off
cd /d "%~dp0App"
if exist "dist\DS4DesktopAdapter\DS4DesktopAdapter.exe" (
  start "" "dist\DS4DesktopAdapter\DS4DesktopAdapter.exe"
) else if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "main.py"
) else (
  echo Run App\setup.ps1 first, then open this launcher again.
  pause
)
