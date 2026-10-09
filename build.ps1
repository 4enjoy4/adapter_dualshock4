$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& '.\.venv\Scripts\python.exe' -m pip install 'pyinstaller==6.22.3'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed.' }
& '.\.venv\Scripts\python.exe' -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --windowed --onedir --name DS4DesktopAdapter --hidden-import pystray._win32 --add-data 'assets;assets' main.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
Write-Output 'Built dist\DS4DesktopAdapter\DS4DesktopAdapter.exe'
