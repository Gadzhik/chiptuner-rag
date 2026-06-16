"""Помощник распаковки защищённых паролем .7z.

Требует установленный 7-Zip (https://www.7-zip.org/).
Пароль архива берётся из переменной окружения CHIPTUNER_ARCHIVE_PW (или --password).
Использование:
    CHIPTUNER_ARCHIVE_PW=... python extract_7z.py "archive.7z" "out_dir"
    python extract_7z.py --all "folder_with_7z" "out_dir" --password ...
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

PASSWORD = os.environ.get("CHIPTUNER_ARCHIVE_PW", "")


def find_7z() -> str:
    for c in (r"C:\Program Files\7-Zip\7z.exe",
              r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if Path(c).exists():
            return c
    exe = shutil.which("7z") or shutil.which("7za")
    if exe:
        return exe
    sys.exit("! 7-Zip не найден. Установи: https://www.7-zip.org/")


def unpack(seven: str, archive: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    print(f"-> распаковка {archive.name}")
    cmd = [seven, "x", str(archive), f"-o{out}", f"-p{PASSWORD}", "-y", "-bsp1"]
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        print(f"  ! код выхода {rc} для {archive.name}")
    return rc == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help=".7z файл или папка (с --all)")
    ap.add_argument("out", help="куда распаковать")
    ap.add_argument("--all", action="store_true", help="source = папка, распаковать все .7z")
    ap.add_argument("--password", default=PASSWORD, help="пароль архива (или env CHIPTUNER_ARCHIVE_PW)")
    args = ap.parse_args()

    global PASSWORD
    PASSWORD = args.password
    seven = find_7z()
    src = Path(args.source)
    out = Path(args.out)

    if args.all:
        archives = sorted(src.glob("*.7z"))
        print(f"найдено архивов: {len(archives)}")
        for a in archives:
            unpack(seven, a, out / a.stem)
    else:
        unpack(seven, src, out)


if __name__ == "__main__":
    main()
