# Japan Tour — 로컬 DB(pgvector) + migrate (회사와 동일 .env, POSTGRES_PORT=5432 등)
# 사용: conda activate japantour_env  →  .\scripts\dev-up.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    Write-Error ".env 파일이 없습니다. 회사 PC에서 복사한 .env를 프로젝트 루트에 두세요."
}

function Get-EnvValue([string]$Name) {
    $line = Get-Content ".env" -Encoding UTF8 | Where-Object { $_ -match "^\s*$Name\s*=" } | Select-Object -First 1
    if (-not $line) { return $null }
    $v = ($line -split "=", 2)[1].Trim()
    $v.Trim('"').Trim("'")
}

$pgPort = Get-EnvValue "POSTGRES_PORT"
if (-not $pgPort) { $pgPort = "5432" }

Write-Host "=== 0) pgvector 확인 (.env → port $pgPort) ===" -ForegroundColor Cyan
python scripts\check_pgvector.py
$pgOk = ($LASTEXITCODE -eq 0)

if (-not $pgOk) {
    Write-Host "`n=== 1) Docker Postgres (pgvector) ===" -ForegroundColor Cyan
    try {
        docker info 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "docker daemon not running" }
    } catch {
        Write-Host @"

Docker Desktop이 실행 중이 아닙니다.

1) Docker Desktop 설치 후 실행
2) 다시: .\scripts\dev-up.ps1

5432의 Windows PostgreSQL만 있으면 pgvector가 없어 migrate가 실패합니다.

"@ -ForegroundColor Yellow
        exit 1
    }

    $portListen = Get-NetTCPConnection -LocalPort ([int]$pgPort) -State Listen -ErrorAction SilentlyContinue
    if ($portListen) {
        $pids = $portListen.OwningProcess | Sort-Object -Unique
        Write-Host "포트 $pgPort 사용 중 (PID: $($pids -join ', '))"
        $pgServices = Get-Service -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -match "postgresql" -and $_.Status -eq "Running"
        }
        if ($pgServices) {
            Write-Host "Windows PostgreSQL 중지 → Docker pgvector가 같은 포트($pgPort) 사용:" -ForegroundColor Yellow
            foreach ($svc in $pgServices) {
                Write-Host "  Stop-Service $($svc.Name)"
                Stop-Service -Name $svc.Name -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 2
        }
    }

    docker compose up -d
    if ($LASTEXITCODE -ne 0) {
        Write-Host "docker compose 실패. 포트 $pgPort 충돌 여부 확인 후 재시도." -ForegroundColor Red
        exit 1
    }

    Write-Host "DB 준비 대기..."
    for ($i = 0; $i -lt 45; $i++) {
        docker compose exec -T db pg_isready 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 2
    }

    python scripts\check_pgvector.py
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Docker 기동 후 pgvector 확인 실패. .env의 POSTGRES_PASSWORD/POSTGRES_DB가 컨테이너와 일치하는지 확인하세요."
    }
} else {
    Write-Host "pgvector OK — Docker 생략" -ForegroundColor Green
}

Write-Host "`n=== 2) Django migrate ===" -ForegroundColor Cyan
python backend\manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) {
    Write-Error "migrate 실패"
}

Write-Host "`n=== 완료 ===" -ForegroundColor Green
Write-Host "  python backend\manage.py runserver 127.0.0.1:8000"
Write-Host "  http://127.0.0.1:8000/"
if ((Get-EnvValue "VECTOR_BACKEND") -eq "pgvector") {
    Write-Host ""
    Write-Host "RAG(pgvector) 적재 — 회사 DB 데이터가 없으면:"
    Write-Host "  python backend\manage.py import_tour_knowledge --batch-size 200"
}
