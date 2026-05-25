# 회사와 동일 POSTGRES_PORT=5432 — Windows PostgreSQL 중지 후 Docker pgvector 기동
# 관리자 PowerShell에서 실행:  Right-click PowerShell → "관리자 권한으로 실행"

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "Windows PostgreSQL 중지 (5432 점유 해제)..." -ForegroundColor Yellow
Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "^postgresql" } | ForEach-Object {
    if ($_.Status -eq "Running") {
        Stop-Service $_.Name -Force
        Write-Host "  중지: $($_.Name)"
    }
}

Remove-Item Env:POSTGRES_PORT -ErrorAction SilentlyContinue
docker compose down 2>$null
docker compose up -d

Start-Sleep -Seconds 5
docker ps --filter "name=japantour-pg" --format "table {{.Names}}\t{{.Ports}}\t{{.Status}}"

Write-Host "`n다음 (일반 PowerShell):" -ForegroundColor Cyan
Write-Host "  conda activate japantour_env"
Write-Host "  python scripts\check_pgvector.py"
Write-Host "  python backend\manage.py migrate --noinput"
Write-Host "  python backend\manage.py runserver 127.0.0.1:8000"
