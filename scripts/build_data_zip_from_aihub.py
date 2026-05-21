"""Merge AI Hub TL_* labeling zips under aihub_download into root data.zip for extract_tour_knowledge.py."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEARCH = PROJECT_ROOT / "aihub_download"
DEFAULT_OUT = PROJECT_ROOT / "data.zip"
LABEL_MARKERS = ("TL_", "VL_")  # training + validation labeling archives


def iter_label_zips(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*.zip"):
        name = path.name.upper()
        if any(name.startswith(m) for m in LABEL_MARKERS):
            found.append(path)
    return sorted(found)


def build_data_zip(search_dir: Path, output: Path) -> int:
    zips = iter_label_zips(search_dir)
    if not zips:
        print(f"[ERROR] No TL_/VL_ zip files under: {search_dir}")
        return 1

    json_count = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as out_zip:
        for archive in zips:
            print(f"[INFO] Merging: {archive.relative_to(search_dir)}")
            with zipfile.ZipFile(archive, "r") as inner:
                for info in inner.infolist():
                    if not info.filename.endswith(".json"):
                        continue
                    data = inner.read(info.filename)
                    # extract_tour_knowledge.py requires "02." in the path
                    arcname = f"02.labeling/{archive.stem}/{Path(info.filename).name}"
                    out_zip.writestr(arcname, data)
                    json_count += 1

    print(f"[DONE] Wrote {output} ({json_count:,} JSON files from {len(zips)} archives)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--search-dir", type=Path, default=DEFAULT_SEARCH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    return build_data_zip(args.search_dir.resolve(), args.output.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
