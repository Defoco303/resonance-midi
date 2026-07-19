$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m PyInstaller --noconfirm --clean --onefile --windowed `
  --name "ResonanceMidiPlayer" `
  --version-file "version_info.txt" `
  "qt_app.py"
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller failed with exit code $LASTEXITCODE"
}
Write-Host "Build complete: $PSScriptRoot\dist\ResonanceMidiPlayer.exe"
