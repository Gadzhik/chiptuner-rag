"""Поиск по индексу + формирование ответа через LM Studio."""
import re
import sqlite3
from pathlib import Path

import chromadb

from . import config, embed, lmstudio
from .ingest import COLLECTION

# токены-идентификаторы: EDC17, ME7, MED17, SID807, MSV80, M74 и т.п.
_ID_RE = re.compile(r"[A-Za-z]{2,}\d+[A-Za-z0-9]*")
# латиница-слова (бренды/производители): Bosch, Siemens, Cummins, Volvo, Delphi
_LAT_RE = re.compile(r"[A-Za-z]{4,}")
_STOP = {"como", "како", "edc", "tdi"}  # шум не нужен — _ID_RE покрывает EDC17


def catalog_files(cfg: dict, question: str, limit: int = 8) -> list[dict]:
    """Файлы из catalog.db (прошивки/программы) по идентификаторам ЭБУ/бренда из вопроса."""
    db = Path(cfg["data_dir"]) / "catalog.db"
    if not db.exists():
        return []
    terms = _ID_RE.findall(question)
    terms += [w for w in _LAT_RE.findall(question) if w.lower() not in _STOP and not _ID_RE.fullmatch(w)]
    seen, uniq = set(), []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower()); uniq.append(t)
    uniq = uniq[:5]
    if not uniq:
        return []
    match = " OR ".join(f'"{t}"*' for t in uniq)
    con = sqlite3.connect(db)
    try:
        sql = ("SELECT f.path, f.archive, f.size, f.category, f.ecu, f.brand "
               "FROM files_fts fts JOIN files f ON f.id=fts.rowid "
               "WHERE files_fts MATCH ? AND f.is_dir=0 "
               "ORDER BY CASE f.category WHEN 'firmware' THEN 0 WHEN 'software' THEN 1 "
               "WHEN 'document' THEN 2 ELSE 3 END, f.size DESC LIMIT ?")
        rows = con.execute(sql, [match, limit]).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()
    return [{"path": p, "archive": a, "size": s, "category": c, "ecu": e, "brand": b}
            for p, a, s, c, e, b in rows]

SYSTEM_PROMPT = (
    "Ты — ассистент и наставник чип-тюнера. ПРИОРИТЕТ — предоставленные фрагменты "
    "справочников/курсов: если в них есть ответ, опирайся на них и указывай источники. "
    "Если фрагменты НЕ покрывают вопрос (особенно базовые, понятийные, обучающие вопросы — "
    "что это, чем отличается, как устроено) — всё равно дай полезный понятный ответ из "
    "своих общих знаний о чип-тюнинге и ЭБУ, пометив его '(из общих знаний)'. "
    "НЕ отказывайся отвечать на простые понятийные вопросы фразой 'данных недостаточно' — "
    "так отвечай только если вопрос узкоспецифичный (конкретная прошивка/процедура) и "
    "данных реально нет. Отвечай по-русски, конкретно, с практическими шагами. "
    "В конце перечисли источники-фрагменты, которые реально использовал."
)


def get_collection(cfg: dict):
    client = chromadb.PersistentClient(path=str(Path(cfg["data_dir"]) / "chroma"))
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def retrieve(cfg: dict, col, question: str) -> list[dict]:
    qv = embed.embed_query(cfg["embedding_model"], question)
    res = col.query(query_embeddings=[qv], n_results=cfg["top_k"],
                    include=["documents", "metadatas", "distances"])
    hits = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"text": doc, "name": meta["name"], "path": meta["path"], "score": 1 - dist})
    return hits


def build_context(hits: list[dict], max_chars: int = 3500) -> str:
    """Склеить фрагменты в контекст, не превышая бюджет символов — иначе промпт
    вылезет за n_ctx модели (LM Studio: 'tokens to keep > context length')."""
    blocks, used = [], 0
    for i, h in enumerate(hits, 1):
        head = f"[Фрагмент {i} — {h['name']}]\n"
        room = max_chars - used - len(head)
        if room <= 80:           # места почти нет — дальше не добавляем
            break
        text = h["text"]
        if len(text) > room:     # последний фрагмент подрезаем по бюджету
            text = text[:room].rsplit(" ", 1)[0] + " …"
        blocks.append(head + text)
        used += len(head) + len(text) + 2
    return "\n\n".join(blocks)


def answer(cfg: dict, col, question: str, stream: bool = True) -> dict:
    hits = retrieve(cfg, col, question)
    if not hits:
        return {"answer": "В индексе нет данных. Сначала запусти ingest.", "sources": []}
    context = build_context(hits, cfg.get("max_context_chars", 3500))
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Фрагменты:\n{context}\n\nВопрос: {question}"},
    ]
    txt = lmstudio.chat(cfg["lmstudio"], messages, stream=stream)
    return {"answer": txt,
            "sources": [{"name": h["name"], "path": h["path"],
                         "score": round(h["score"], 3)} for h in hits],
            "files": catalog_files(cfg, question)}
