param([string]$Service = "consensus-api")

Write-Host "Cleaning build and Python cache for $Service..." -ForegroundColor Cyan

# Python cache temizligi
Get-ChildItem -Recurse -Filter __pycache__ -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -Filter .pytest_cache -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -Filter *.pyc -ErrorAction SilentlyContinue | Remove-Item -Force

# Docker builder cache temizligi
docker builder prune -f --filter "label=service=$Service"

# Servisi rebuild et
Write-Host "Rebuilding $Service..." -ForegroundColor Cyan
docker compose build --no-cache --progress=plain $Service
docker compose up -d $Service

Write-Host "Done." -ForegroundColor Green
