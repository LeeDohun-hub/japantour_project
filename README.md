# japantour_project

**대표·이해관계자용 한국어 문서:** [`docs/japantour/README.md`](docs/japantour/README.md) (개발환경, 개요, 요구사항, 기본설계)

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
3. Optional: `AIHUB_APIKEY` for AI Hub downloads (`DATA_SETUP.md`). Other keys in `.env.example` are for optional `src/` experiments.

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

## Notes

- `.gitignore` contains `/data` and `.env`, so dataset files and secrets are not committed.
- For detailed data setup examples, see `DATA_SETUP.md`.
