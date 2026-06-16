"""Индексация: обход папок -> извлечение текста -> чанки -> embeddings -> ChromaDB.

Запуск:
    python -m src.ingest            # индексировать всё из config.docs_dirs
    python -m src.ingest --reset    # очистить индекс и заново
"""
import argparse
import hashlib
from pathlib import Path

import chromadb
from tqdm import tqdm

from . import config, embed, textextract

COLLECTION = "chiptuner_docs"


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    text = "\n".join(ln.rstrip() for ln in text.splitlines())
    chunks, i, n = [], 0, len(text)
    step = max(size - overlap, 1)
    while i < n:
        end = min(i + size, n)
        # пытаемся резать по границе абзаца/предложения
        if end < n:
            br = text.rfind("\n", i + size // 2, end)
            if br == -1:
                br = text.rfind(". ", i + size // 2, end)
            if br != -1 and br > i + size // 2:
                end = br
        piece = text[i:end].strip()
        if len(piece) > 40:
            chunks.append(piece)
        i = end if end >= i + step else i + step
    return chunks


def file_id(path: Path) -> str:
    return hashlib.md5(str(path).encode("utf-8")).hexdigest()[:12]


def iter_files(dirs: list[str]):
    for d in dirs:
        base = Path(d)
        if not base.exists():
            print(f"[ingest] ПРОПУСК: нет папки {base}")
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in textextract.SUPPORTED:
                yield p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="очистить индекс перед началом")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    cfg = config.load(args.config)
    data_dir = Path(cfg["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(data_dir / "chroma"))
    if args.reset:
        try:
            client.delete_collection(COLLECTION)
            print("[ingest] индекс очищен")
        except Exception:  # noqa: BLE001
            pass
    col = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    files = list(iter_files(cfg["docs_dirs"]))
    print(f"[ingest] найдено файлов: {len(files)}")

    added = 0
    for path in tqdm(files, desc="файлы"):
        fid = file_id(path)
        # пропуск уже проиндексированного файла (по префиксу id)
        existing = col.get(where={"fid": fid}, limit=1)
        if existing["ids"]:
            continue
        text = textextract.extract(path)
        if not text.strip():
            continue
        chunks = chunk_text(text, cfg["chunk_chars"], cfg["chunk_overlap"])
        if not chunks:
            continue
        vecs = embed.embed_passages(cfg["embedding_model"], chunks)
        ids = [f"{fid}_{i}" for i in range(len(chunks))]
        metas = [{"fid": fid, "path": str(path), "name": path.name, "chunk": i}
                 for i in range(len(chunks))]
        # ChromaDB ограничивает размер одного add (~5461). Бьём на пачки.
        BATCH = 4000
        for j in range(0, len(chunks), BATCH):
            sl = slice(j, j + BATCH)
            col.add(ids=ids[sl], documents=chunks[sl],
                    embeddings=vecs[sl], metadatas=metas[sl])
        added += len(chunks)

    print(f"[ingest] готово. добавлено чанков: {added}. всего в индексе: {col.count()}")


if __name__ == "__main__":
    main()
