"""Поиск по каталогу.

    python -m src.cat_search "EDC17"                 # полнотекст по пути
    python -m src.cat_search --brand "Mercedes-Benz"
    python -m src.cat_search --ecu "Bosch EDC17" --ext pdf
    python -m src.cat_search --stats                  # сводка
"""
import argparse
import sqlite3
from pathlib import Path

from . import config


def connect():
    cfg = config.load()
    return sqlite3.connect(Path(cfg["data_dir"]) / "catalog.db")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", help="полнотекстовый запрос по пути")
    ap.add_argument("--brand")
    ap.add_argument("--ecu")
    ap.add_argument("--ext")
    ap.add_argument("--category")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    con = connect()

    if args.stats:
        print("--- по брендам ---")
        for b, n in con.execute("SELECT brand,COUNT(*) FROM files WHERE brand IS NOT NULL"
                                " AND is_dir=0 GROUP BY brand ORDER BY 2 DESC"):
            print(f"  {b:22} {n}")
        print("--- по ECU ---")
        for e, n in con.execute("SELECT ecu,COUNT(*) FROM files WHERE ecu IS NOT NULL"
                                " AND is_dir=0 GROUP BY ecu ORDER BY 2 DESC"):
            print(f"  {e:32} {n}")
        print("--- по категориям ---")
        for c, n, gb in con.execute("SELECT category,COUNT(*),SUM(size)/1e9 FROM files"
                                    " WHERE is_dir=0 GROUP BY category ORDER BY 2 DESC"):
            print(f"  {c:10} {n:8}  {gb or 0:8.1f} GB")
        return

    where, params = ["is_dir=0"], []
    if args.brand:
        where.append("brand=?"); params.append(args.brand)
    if args.ecu:
        where.append("ecu=?"); params.append(args.ecu)
    if args.ext:
        where.append("ext=?"); params.append(args.ext.lower())
    if args.category:
        where.append("category=?"); params.append(args.category)

    if args.query:
        # префиксный поиск: каждое простое слово -> слово* (EDC17 найдёт EDC17C46)
        terms = args.query.split()
        if all(t.isalnum() for t in terms):
            match = " ".join(f"{t}*" for t in terms)
        else:
            match = args.query
        sql = ("SELECT f.archive,f.path,f.size FROM files_fts fts"
               " JOIN files f ON f.id=fts.rowid"
               " WHERE files_fts MATCH ? AND " + " AND ".join(where) +
               " LIMIT ?")
        params = [match] + params + [args.limit]
    else:
        sql = ("SELECT archive,path,size FROM files WHERE " + " AND ".join(where) +
               " LIMIT ?")
        params = params + [args.limit]

    rows = con.execute(sql, params).fetchall()
    for arch, path, size in rows:
        print(f"  [{size/1e6:7.1f} MB] {path}")
        print(f"            в архиве: {arch}")
    print(f"\nнайдено (показано {len(rows)})")


if __name__ == "__main__":
    main()
