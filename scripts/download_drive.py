"""Download field recordings from the shared Drive, skipping the unused folder."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FOLDER = "https://drive.google.com/drive/folders/1hplLntZNSf7ftGv8oj2MKGrx8bm59rQI"
DEST = Path("data/field")
SKIP_PREFIXES = (
    "15_08 açude 2 (esse nao precisa)",
    "Áudio base",
    "Audio base",
)


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    raw = subprocess.check_output(
        ["gdown", FOLDER, "--folder", "--json", "--quiet"],
        text=True,
    )
    items = json.loads(raw)
    todo = []
    for item in items:
        path = item["path"].replace("\\", "/")
        if any(path.startswith(p) or f"/{p}/" in f"/{path}" for p in SKIP_PREFIXES):
            print(f"skip {path}")
            continue
        dest = DEST / path
        todo.append((item["url"], dest, path))

    print(f"{len(todo)} files to download")
    for i, (url, dest, path) in enumerate(todo, 1):
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 0:
            print(f"[{i}/{len(todo)}] exists {path} ({dest.stat().st_size} bytes)")
            continue
        print(f"[{i}/{len(todo)}] {path}")
        subprocess.check_call(["gdown", url, "-O", str(dest), "--continue"])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
