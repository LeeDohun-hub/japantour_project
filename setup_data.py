import argparse
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path


def download_file(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Downloading: {url}")
    urllib.request.urlretrieve(url, output_path)
    print(f"[INFO] Saved archive to: {output_path}")


def copy_directory_contents(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        target = dst_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def extract_zip(zip_path: Path, dst_dir: Path) -> None:
    if not zip_path.exists():
        raise FileNotFoundError(f"Zip file not found: {zip_path}")
    dst_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dst_dir)


def prepare_target_directory(dst_dir: Path, force: bool) -> None:
    if dst_dir.exists() and force:
        print(f"[INFO] Removing existing directory: {dst_dir}")
        shutil.rmtree(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set up ignored ./data directory from local folder, zip, or URL."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--source-dir",
        type=Path,
        help="Path to local directory containing dataset files.",
    )
    source_group.add_argument(
        "--source-zip",
        type=Path,
        help="Path to local zip archive containing dataset files.",
    )
    source_group.add_argument(
        "--download-url",
        type=str,
        help="URL to download a zip archive before extraction.",
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Target data directory (default: ./data).",
    )
    parser.add_argument(
        "--download-to",
        type=Path,
        default=Path("data_archive.zip"),
        help="Archive path used with --download-url (default: ./data_archive.zip).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete existing data directory before setup.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    data_dir = args.data_dir
    prepare_target_directory(data_dir, args.force)

    if args.source_dir:
        src_dir = args.source_dir
        if not src_dir.exists() or not src_dir.is_dir():
            print(f"[ERROR] source directory does not exist: {src_dir}")
            return 1
        copy_directory_contents(src_dir, data_dir)
        print(f"[INFO] Data copied from directory: {src_dir}")

    elif args.source_zip:
        extract_zip(args.source_zip, data_dir)
        print(f"[INFO] Data extracted from zip: {args.source_zip}")

    elif args.download_url:
        archive_path = args.download_to
        download_file(args.download_url, archive_path)
        extract_zip(archive_path, data_dir)
        print(f"[INFO] Data downloaded and extracted into: {data_dir}")

    else:
        print("[ERROR] No valid source option was provided.")
        return 1

    print("[INFO] Data setup completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
