# Data Setup Guide

This project ignores the `data` directory via `.gitignore`.
Use `setup_data.py` to restore `data` after cloning.

## 1) Install Python dependencies

```bash
pip install -r requirements.txt
```

## 2) Set up data (choose one)

### Option A: Copy from local directory

```bash
python setup_data.py --source-dir "D:\datasets\japantour_data" --force
```

### Option B: Extract from local zip

```bash
python setup_data.py --source-zip "D:\datasets\japantour_data.zip" --force
```

### Option C: Download zip from URL and extract

```bash
python setup_data.py --download-url "https://example.com/japantour_data.zip" --force
```

Optional:

- `--data-dir "<path>"`: set target directory (default: `./data`)
- `--download-to "<path>"`: set downloaded archive path (default: `./data_archive.zip`)
- `--force`: remove existing `data` directory before setup
