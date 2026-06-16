"""Полная распаковка НЕ-видео архивов настоящим 7-Zip (py7zr не тянет AES+каскад>4).

Поток: для каждого нужного .7z внутри Кладезь.zip -> вынуть в _work -> 7z x с паролем
в _unpacked/<короткое_имя> -> .done маркер -> удалить temp .7z.
Короткие имена папок, чтобы не упираться в длинные пути.

Запуск:
    python -m src.unpack                 # все не-видео
    python -m src.unpack --only fw_2015   # только цели, чьё короткое имя содержит строку
"""
import argparse
import os
import subprocess
import time
import zipfile
from pathlib import Path

from . import config

_cfg = config.load()
# Секреты/пути не хардкодим: пароль — из env или config, путь к zip — из config.
PASSWORD = os.environ.get("CHIPTUNER_ARCHIVE_PW") or _cfg.get("archive_password", "")
ZIP_PATH = _cfg.get("archive_zip", "")
SEVENZIP = r"C:\Program Files\7-Zip\7z.exe"

# подстрока в имени .7z  ->  короткое имя папки назначения
TARGETS = {
    "СПРАВОЧНИК": "spravochnik",
    "Энциклопедия": "encyclopedia",
    ".ПРОШИВКИ 2015-2019": "fw_2015_2019",
    ".ПРОШИВКИ 2020": "fw_2020",
    "Программы для Диагностики": "prog_diag",
    "ПРОГРАММЫ для Чип Тюнинга": "prog_chip",
    "Редакторы": "editors",
    "отключения IMMO": "immo_off",
    "Kess 5.017": "kess_ktag",
    "Энкодеры": "encoders",
    "Мануалы группы VAG": "vag",
    "Секреты рекламы": "secrets",
}


def short_name(archive_filename: str) -> str | None:
    for sub, short in TARGETS.items():
        if sub in archive_filename:
            return short
    return None


def extract_member(zf: zipfile.ZipFile, member: str, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(member) as src, open(out, "wb") as dst:
        while True:
            b = src.read(16 * 1024 * 1024)
            if not b:
                break
            dst.write(b)


def run_7z(archive: Path, dest: Path) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [SEVENZIP, "x", str(archive), f"-o{dest}", f"-p{PASSWORD}",
           "-aoa", "-y", "-bsp1", "-bso0"]
    rc = subprocess.run(cmd).returncode
    return rc == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="только цели, чьё короткое имя содержит строку")
    ap.add_argument("--work", default="F:/filat/_work")
    ap.add_argument("--out", default="F:/filat/_unpacked")
    args = ap.parse_args()

    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    out_root = Path(args.out); out_root.mkdir(parents=True, exist_ok=True)

    zf = zipfile.ZipFile(ZIP_PATH)
    jobs = []
    for info in zf.infolist():
        if not info.filename.lower().endswith(".7z"):
            continue
        short = short_name(info.filename)
        if short is None:
            continue  # видео-курс или не цель
        if args.only and args.only.lower() not in short.lower():
            continue
        jobs.append((info, short))

    jobs.sort(key=lambda j: j[0].file_size)  # мелкие доки первыми, прошивки последними
    print(f"[unpack] целей: {len(jobs)}")
    for i, (info, short) in enumerate(jobs, 1):
        dest = out_root / short
        done_marker = out_root / f"{short}.done"
        if done_marker.exists():
            print(f"[{i}/{len(jobs)}] пропуск (готово): {short}")
            continue
        tmp = work / (short + ".7z")
        print(f"[{i}/{len(jobs)}] {short}  ({info.file_size/1e9:.2f} GB) <- {info.filename}")
        t = time.time()
        extract_member(zf, info.filename, tmp)
        print(f"   вынут за {time.time()-t:.0f}s, распаковка 7z -> {dest}")
        te = time.time()
        ok = run_7z(tmp, dest)
        if ok:
            done_marker.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
            print(f"   OK ({time.time()-te:.0f}s)")
        else:
            print(f"   ! 7z вернул ошибку для {short}")
        if tmp.exists():
            tmp.unlink()

    print("[unpack] готово")


if __name__ == "__main__":
    main()
