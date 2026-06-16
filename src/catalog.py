"""Каталог архива «Кладезь» в SQLite (без полной распаковки).

Логика: для каждого .7z внутри Кладезь.zip — вынуть на диск, прочитать ОГЛАВЛЕНИЕ
(py7zr.list(), содержимое НЕ распаковывается), записать в БД, удалить временный .7z.
Пик занятого места = самый большой .7z (~92 ГБ). Процесс возобновляемый.

Запуск:
    python -m src.catalog                       # каталог всех 22 .7z из zip
    python -m src.catalog --only СПРАВОЧНИК      # только архивы, чьё имя содержит строку
    python -m src.catalog --dir F:/filat/_unpacked   # каталог уже распакованных файлов
    python -m src.catalog --keep                 # не удалять временные .7z после листинга
"""
import argparse
import os
import sqlite3
import time
import zipfile
from pathlib import Path

import py7zr

from . import config, classify

_cfg = config.load()
# Секреты/пути не хардкодим: пароль архива — из env или config, путь к zip — из config.
PASSWORD = os.environ.get("CHIPTUNER_ARCHIVE_PW") or _cfg.get("archive_password", "")
ZIP_PATH = _cfg.get("archive_zip", "")


def db_connect(data_dir: Path) -> sqlite3.Connection:
    data_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(data_dir / "catalog.db")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS archives(
        name TEXT PRIMARY KEY, files INTEGER, bytes INTEGER, cataloged_at TEXT);
    CREATE TABLE IF NOT EXISTS files(
        id INTEGER PRIMARY KEY,
        archive TEXT, path TEXT, name TEXT, ext TEXT,
        size INTEGER, crc TEXT, is_dir INTEGER,
        brand TEXT, ecu TEXT, category TEXT);
    CREATE INDEX IF NOT EXISTS i_name ON files(name);
    CREATE INDEX IF NOT EXISTS i_ext ON files(ext);
    CREATE INDEX IF NOT EXISTS i_brand ON files(brand);
    CREATE INDEX IF NOT EXISTS i_ecu ON files(ecu);
    CREATE INDEX IF NOT EXISTS i_cat ON files(category);
    CREATE VIRTUAL TABLE IF NOT EXISTS files_fts
        USING fts5(path, content='files', content_rowid='id', tokenize='unicode61');
    """)
    return con


def record_entries(con, archive_name: str, entries):
    rows = []
    nfiles = 0
    nbytes = 0
    for fi in entries:
        fn = fi.filename
        name = fn.rsplit("/", 1)[-1]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        is_dir = 1 if fi.is_directory else 0
        if not is_dir:
            nfiles += 1
            nbytes += fi.uncompressed
        category, brand, ecu = classify.classify(fn, ext)
        crc = f"{fi.crc32:08x}" if getattr(fi, "crc32", None) else None
        rows.append((archive_name, fn, name, ext, fi.uncompressed, crc, is_dir,
                     brand, ecu, category))
    cur = con.cursor()
    cur.execute("DELETE FROM files WHERE archive=?", (archive_name,))
    cur.executemany(
        "INSERT INTO files(archive,path,name,ext,size,crc,is_dir,brand,ecu,category)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
    # FTS
    cur.execute(
        "INSERT INTO files_fts(rowid,path) SELECT id,path FROM files WHERE archive=?",
        (archive_name,))
    con.execute(
        "INSERT OR REPLACE INTO archives(name,files,bytes,cataloged_at) VALUES(?,?,?,?)",
        (archive_name, nfiles, nbytes, time.strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    return nfiles, nbytes


def list_7z(path: Path):
    with py7zr.SevenZipFile(str(path), "r", password=PASSWORD) as a:
        return a.list()


def extract_member(zf: zipfile.ZipFile, member: str, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(member) as src, open(out, "wb") as dst:
        while True:
            b = src.read(16 * 1024 * 1024)
            if not b:
                break
            dst.write(b)


VIDEO_KW = "Уроки"  # архивы-видеокурсы: их НЕ распаковываем полностью (ждут Whisper)


def full_extract(archive: Path, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(str(archive), "r", password=PASSWORD) as a:
        a.extractall(path=str(dest))


def from_zip(con, only: str | None, keep: bool, work: Path, extract_to: Path | None):
    work.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(ZIP_PATH)
    members = [i for i in zf.infolist()
               if i.filename.lower().endswith(".7z")
               and (only is None or only.lower() in i.filename.lower())]
    done = {r[0] for r in con.execute("SELECT name FROM archives")}
    print(f"[catalog] архивов к обработке: {len(members)}")
    for i, info in enumerate(members, 1):
        aname = info.filename.split("/")[-1]
        tmp = work / aname
        is_video = VIDEO_KW in aname
        dest = (extract_to / Path(aname).stem) if extract_to else None
        already_extracted = dest is not None and dest.exists()
        need_catalog = aname not in done
        need_extract = (dest is not None and not is_video and not already_extracted)

        if not need_catalog and not need_extract:
            print(f"[{i}/{len(members)}] пропуск (готово): {aname}")
            continue

        print(f"[{i}/{len(members)}] {aname}  ({info.file_size/1e9:.2f} GB) -> вынимаю...")
        t = time.time()
        extract_member(zf, info.filename, tmp)
        try:
            if need_catalog:
                entries = list_7z(tmp)
                nf, nb = record_entries(con, aname, entries)
                print(f"   каталог: {nf} файлов, {nb/1e9:.2f} GB  ({time.time()-t:.0f}s)")
            if need_extract:
                print(f"   распаковка -> {dest} ...")
                te = time.time()
                full_extract(tmp, dest)
                print(f"   распаковано ({time.time()-te:.0f}s)")
            elif is_video and extract_to:
                print("   видео-курс: полная распаковка пропущена (ждёт Whisper)")
        except Exception as e:  # noqa: BLE001
            print(f"   ! ошибка: {type(e).__name__}: {e}")
        finally:
            if not keep and tmp.exists():
                tmp.unlink()


def from_dir(con, root: Path):
    print(f"[catalog] обход {root}")
    rows = []
    for p in root.rglob("*"):
        is_dir = p.is_dir()
        name = p.name
        ext = name.rsplit(".", 1)[-1].lower() if "." in name and not is_dir else ""
        size = p.stat().st_size if not is_dir else 0
        rel = str(p)
        category, brand, ecu = classify.classify(rel, ext)
        rows.append(("(disk)", rel, name, ext, size, None, 1 if is_dir else 0,
                     brand, ecu, category))
    cur = con.cursor()
    cur.execute("DELETE FROM files WHERE archive='(disk)'")
    cur.executemany(
        "INSERT INTO files(archive,path,name,ext,size,crc,is_dir,brand,ecu,category)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)", rows)
    cur.execute("INSERT INTO files_fts(rowid,path) SELECT id,path FROM files WHERE archive='(disk)'")
    con.commit()
    print(f"[catalog] записано {len(rows)} строк с диска")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="обрабатывать только архивы, чьё имя содержит строку")
    ap.add_argument("--dir", help="каталог уже распакованной папки вместо zip")
    ap.add_argument("--keep", action="store_true", help="не удалять временные .7z")
    ap.add_argument("--work", default="F:/filat/_work", help="папка для временных .7z")
    ap.add_argument("--extract-to", help="полностью распаковать НЕ-видео архивы сюда")
    args = ap.parse_args()

    cfg = config.load()
    con = db_connect(Path(cfg["data_dir"]))

    if args.dir:
        from_dir(con, Path(args.dir))
    else:
        extract_to = Path(args.extract_to) if args.extract_to else None
        from_zip(con, args.only, args.keep, Path(args.work), extract_to)

    # сводка
    print("\n=== СВОДКА ===")
    for cat, n, gb in con.execute(
            "SELECT category,COUNT(*),SUM(size)/1e9 FROM files WHERE is_dir=0"
            " GROUP BY category ORDER BY 2 DESC"):
        print(f"  {cat:10} {n:8} файлов  {gb or 0:8.1f} GB")
    total = con.execute("SELECT COUNT(*) FROM files WHERE is_dir=0").fetchone()[0]
    print(f"  ВСЕГО: {total} файлов")
    con.close()


if __name__ == "__main__":
    main()
