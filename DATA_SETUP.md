# Data Setup Guide (Japan Tour Project)

This project ignores the `data` directory via `.gitignore`.
Use `setup_data.py` together with your AI Hub datasets to restore `data` after cloning.

---

## 1) Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## 2) Prepare AI Hub dataset (with `AIHUB_APIKEY`)

1. `.env`에 AI Hub 키가 설정되어 있는지 확인합니다.

```env
AIHUB_APIKEY=893203AE-AEAE-42BA-9823-832363F3D74C
```

2. Git Bash 또는 WSL 등 **bash** 환경에서 `aihubshell`을 실행해,  
   **하나의 데이터셋에 포함된 모든 분할 압축 파일을 한 번에** 다운로드합니다.

   - `-datasetkey`만 지정하고 `-filekey`는 생략하면, 해당 데이터셋의 **전체 파일(`fileSn=all`)**을 받습니다.

예시 1) 일반적인 패턴 (dataSetSn 값을 그대로 사용)

```bash
cd C:/Workspaces/japantour_project

export AIHUB_APIKEY=893203AE-AEAE-42BA-9823-832363F3D74C  # 또는 .env에서 export
./aihubshell -mode d -datasetkey <dataSetSn>
```

예시 2) 생성형AI K-Culture 관광 콘텐츠 특화 일본어 말뭉치 데이터  
([AI Hub 페이지](https://aihub.or.kr/aihubdata/data/view.do?dataSetSn=71789))

```bash
cd C:/Workspaces/japantour_project

export AIHUB_APIKEY=893203AE-AEAE-42BA-9823-832363F3D74C
./aihubshell -mode d -datasetkey 71789
```

- `aihubshell`이 `download.tar`를 받은 뒤 자동으로 압축을 풀고, 분할 파일을 병합합니다.
- 결과 폴더 구조는 데이터셋마다 다르므로, **원하는 CSV/JSON 파일을 골라서 `data/raw/` 쪽으로 정리**하면 됩니다.

3. Windows PowerShell에서 환경변수를 설정하고 bash를 호출하는 방법 예시:

```powershell
cd C:\Workspaces\japantour_project
$env:AIHUB_APIKEY = "893203AE-AEAE-42BA-9823-832363F3D74C"
bash ./aihubshell -mode d -datasetkey 71789
```

---

## 3) Copy processed source files into `./data`

AI Hub에서 받은 원본 파일들을 정리해, 최종적으로 다음과 같은 구조가 되도록 준비합니다.

```bash
japantour_project/
└── data/
    └── raw/
        └── tour_knowledge.csv   # 여행 Q&A 지식 데이터
```

- `tour_knowledge.csv`의 스키마와 예시는 `DATA_PREPROCESSING.md`를 참고하세요.

원본 데이터를 다른 경로에 보관하고 싶다면 먼저 거기에 모은 뒤,
아래 `setup_data.py`를 이용해 `./data`로 복사할 수 있습니다.

---

## 4) Use `setup_data.py` (choose one)

### Option A: Copy from local directory

AI Hub에서 받은 파일들을 미리 `D:\datasets\japantour_data`에 모아 두었다면:

```bash
python setup_data.py --source-dir "D:\datasets\japantour_data" --force
```

### Option B: Extract from local zip

```bash
python setup_data.py --source-zip "D:\datasets\japantour_data.zip" --force
```

Optional flags:

- `--data-dir "<path>"`: set target directory (default: `./data`)
- `--download-to "<path>"`: set downloaded archive path (default: `./data_archive.zip`)
- `--force`: remove existing `data` directory before setup
