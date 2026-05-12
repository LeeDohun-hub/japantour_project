# japantour_project

**1. 팀·프로젝트 소개, 2. 개요, 3. 기술 스택, 4. 핵심 기능, 5. 모델 워크플로, 6. 배포:** [`docs/japantour/README.md`](docs/japantour/README.md)

**개발 환경·요구사항·기본 설계 상세:** [`docs/japantour/`](docs/japantour/) (`01`~`04`)

`data` directory is intentionally ignored in Git.
After cloning, set up dependencies and restore data with the steps below.

## 1) Install dependencies

```bash
pip install -r requirements.txt
```

## 2) Environment variables (`.env`)

1. Copy the example file to `.env` in the project root.
   - **PowerShell:** `Copy-Item .env.example .env`
   - **bash:** `cp .env.example .env`
2. Edit `.env` and set at least **`OPENAI_API_KEY`** for the Streamlit chatbot (`streamlit run app_japan_tour.py`).
3. Set **`GOOGLE_MAPS_API_KEY`** to use current-location nearby tourist spot and cafe recommendations through Google Places API.
4. Optional: `AIHUB_APIKEY` for AI Hub downloads (`DATA_SETUP.md`). Other keys in `.env.example` are for optional `src/` experiments.

## 3) Restore `data` directory

Use one of these methods:

### A. From local directory

```bash
python setup_data.py --source-dir "D:\datasets\japantour_data" --force
```

### B. From local zip archive

```bash
python setup_data.py --source-zip "D:\datasets\japantour_data.zip" --force
```

### C. Download zip from URL and extract

```bash
python setup_data.py --download-url "https://example.com/japantour_data.zip" --force
```

## 4) Useful options

- `--data-dir "<path>"`: target data directory (default: `./data`)
- `--download-to "<path>"`: archive save path for `--download-url` (default: `./data_archive.zip`)
- `--force`: remove existing `data` directory before setup

## 5) Web UI

### Streamlit (기존 단일 앱)

```bash
streamlit run app_japan_tour.py
```

### 프론트엔드 + 백엔드 분리 (HTML/CSS/JS + **Django**)

저장소 루트에서 (최초 1회 DB 파일 생성):

```powershell
cd c:\WorkSpace\japantour_project
python backend\manage.py migrate --noinput
python backend\manage.py runserver 127.0.0.1:8000
```

브라우저: **http://127.0.0.1:8000/** 는 홈, **http://127.0.0.1:8000/chat/** 는 AI 채팅입니다. API는 `/api/health/`, `/api/chat/` 입니다. `OPENAI_API_KEY`가 없으면 채팅은 안내 문구만 반환합니다.

선택 환경 변수: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` (쉼표 구분).

## Notes

- `.gitignore` contains `/data` and `.env`, so dataset files and secrets are not committed.
- For detailed data setup examples, see `DATA_SETUP.md`.
