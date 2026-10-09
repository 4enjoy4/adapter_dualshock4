@echo off
cd /d "%~dp0"
if exist "dist\DS4DesktopAdapter\DS4DesktopAdapter.exe" (
  start "" "dist\DS4DesktopAdapter\DS4DesktopAdapter.exe"
) else if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "main.py"
) else (
  echo Run setup.ps1 first, or use the packaged DS4DesktopAdapter.exe.
  pause
)
