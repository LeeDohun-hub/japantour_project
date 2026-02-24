# japantour_project

`data` directory is intentionally ignored in Git.
After cloning, set up dependencies and restore data with the steps below.

## 1) Install dependencies

```bash
pip install -r requirements.txt
```

## 2) Restore `data` directory

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

## 3) Useful options

- `--data-dir "<path>"`: target data directory (default: `./data`)
- `--download-to "<path>"`: archive save path for `--download-url` (default: `./data_archive.zip`)
- `--force`: remove existing `data` directory before setup

## Notes

- `.gitignore` contains `/data`, so dataset files are not committed.
- For detailed data setup examples, see `DATA_SETUP.md`.
