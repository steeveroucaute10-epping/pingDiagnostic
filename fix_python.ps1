# Fix Python command in PowerShell
# Run this script: .\fix_python.ps1

Write-Host "Setting up Python command..." -ForegroundColor Cyan

# Remove any existing python alias/function
Remove-Item alias:python -ErrorAction SilentlyContinue
Remove-Item function:python -ErrorAction SilentlyContinue

# Define python as a function
function python {
    & "C:\Users\felix\AppData\Local\Python\bin\python.exe" $args
}

Write-Host "Python function loaded!" -ForegroundColor Green
Write-Host "Testing..." -ForegroundColor Cyan
python --version

Write-Host "`nTo make this permanent, run: . `$PROFILE" -ForegroundColor Yellow
Write-Host "Or disable Windows Store alias in Settings > Apps > Advanced app settings > App execution aliases" -ForegroundColor Yellow





