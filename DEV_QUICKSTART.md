# pull 직후 실행 (집 PC · 회사와 동일 `.env`)

## 원인 (한 줄)

회사와 같이 **`POSTGRES_PORT=5432`** 인데, 집 PC는 **5432에 Windows PostgreSQL**(pgvector 없음)이 먼저 떠 있으면 Django가 Docker가 아닌 그쪽으로 붙습니다.

**회사 5432 = pgvector 있는 Postgres 하나만** 5432를 써야 합니다.

## 실행 — 회사와 동일 5432

**① 관리자 PowerShell** (시작 메뉴 → PowerShell → 우클릭 → 관리자 권한)

```powershell
cd C:\Workspaces\japantour_project
.\scripts\start-db-5432.ps1
```

**② 일반 PowerShell**

```powershell
cd C:\Workspaces\japantour_project
conda activate japantour_env
python scripts\check_pgvector.py
python backend\manage.py migrate --noinput
python backend\manage.py runserver 127.0.0.1:8000
```

`check_pgvector.py`가 **OK**가 아니면 5432가 아직 Windows Postgres입니다. ①을 관리자로 다시 실행하세요.

브라우저: http://127.0.0.1:8000/

## `dev-up.ps1`이 하는 일

1. `.env`의 `POSTGRES_PORT`(지금 **5432**)로 pgvector 연결 확인  
2. 없으면 **Windows PostgreSQL 서비스 중지** → **Docker `japantour-pg`** 기동 (같은 포트)  
3. `python backend\manage.py migrate`

`.env`는 **수정하지 않습니다** (회사와 동일).

## PC 재부팅 후

```powershell
docker start japantour-pg
python backend\manage.py runserver 127.0.0.1:8000
```

또는 `.\scripts\dev-up.ps1` 다시 실행.

## `VECTOR_BACKEND=pgvector` (회사와 동일)

채팅 RAG가 DB 벡터를 쓰려면 (회사에서 적재했다면 집 DB는 비어 있음):

```powershell
python backend\manage.py import_tour_knowledge --batch-size 200
```

`data/processed/tour_knowledge.jsonl` 필요. 시간·OpenAI API 소요.

## 확인

```powershell
python scripts\check_pgvector.py
curl http://127.0.0.1:8000/api/health/
```
