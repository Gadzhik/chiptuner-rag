"""Глоссарий для тьютора: авто-определения терминов из энциклопедии (через RAG).

Сборка (один раз, нужен индекс + LM Studio НЕ нужен, только эмбеддинги):
    python -m src.glossary --build      # -> _data/glossary.json

Для каждого термина из tutor_data.GLOSSARY_SEED берём лучший фрагмент из индекса
(семантический поиск, без LLM — мгновенно после загрузки модели эмбеддингов),
вырезаем чистый кусок текста вокруг термина -> определение `enc` + файл-источник.
`short` (ручная расшифровка) остаётся как заголовок/фолбэк.

Рантайм (web): glossary.load() читает JSON, glossary.search() — подстрочный поиск.
Ничего тяжёлого при ответе пользователю.
"""
import argparse
import json
import re
from pathlib import Path

from . import config
from .tutor_data import GLOSSARY_SEED

JSON_NAME = "glossary.json"
_cache = None


def _path(cfg: dict) -> Path:
    return Path(cfg["data_dir"]) / JSON_NAME


def _is_clean_ru(s: str) -> bool:
    """Отсев моябейка/латинского шифра: нужна доля кириллицы среди букв."""
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 30:
        return False
    cyr = sum(1 for c in letters if "а" <= c.lower() <= "я" or c.lower() == "ё")
    return cyr / len(letters) >= 0.6


def _clean_snippet(text: str, term: str, span: int = 280) -> str:
    """Вырезать читаемый кусок вокруг первого упоминания термина."""
    flat = re.sub(r"\s+", " ", text).strip()
    low, tl = flat.lower(), term.lower()
    i = low.find(tl)
    if i == -1:
        snip = flat[:span]
    else:
        start = max(0, i - span // 3)
        snip = flat[start:start + span]
        # не начинать с середины слова
        if start > 0:
            sp = snip.find(" ")
            if 0 < sp < 30:
                snip = snip[sp + 1:]
    snip = snip.strip(" .,:;—-")
    # обрезать до конца предложения, если близко к концу
    last = snip.rfind(". ")
    if last > len(snip) * 0.5:
        snip = snip[:last + 1]
    return snip


def build(cfg: dict) -> list[dict]:
    """Собрать глоссарий: для каждого термина — определение из энциклопедии."""
    from . import embed, rag  # тяжёлые импорты только при сборке

    col = rag.get_collection(cfg)
    out = []
    for term, short in GLOSSARY_SEED:
        enc, source = "", ""
        word = term.split()[0].lower()   # для многословных — первое слово
        try:
            qv = embed.embed_query(cfg["embedding_model"], f"{term} — это что такое, определение")
            res = col.query(query_embeddings=[qv], n_results=10,
                            include=["documents", "metadatas", "distances"])
            docs = res["documents"][0] if res["documents"] else []
            metas = res["metadatas"][0] if res["metadatas"] else []
            dists = res["distances"][0] if res["distances"] else []
            for doc, meta, dist in zip(docs, metas, dists):
                if 1 - dist < 0.30:                      # семантически далеко
                    continue
                path = (meta.get("path") or "").lower()
                if "encyclopedia" not in path:           # только энциклопедия чип-тюнера
                    continue
                if word not in doc.lower():              # термин обязан быть в тексте
                    continue
                snip = _clean_snippet(doc, term)
                if not _is_clean_ru(snip):               # отсев моябейка/латин-шифра
                    continue
                enc, source = snip, meta.get("name", "")
                break
        except Exception as ex:  # noqa: BLE001 — индекс может быть пуст/недоступен
            print(f"[glossary] {term}: пропуск ({ex})")
        out.append({"term": term, "short": short, "enc": enc, "source": source})
        print(f"[glossary] {term}: {'из энциклопедии' if enc else 'только short'}")

    p = _path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[glossary] готово: {len(out)} терминов -> {p}")
    return out


def load(cfg: dict) -> list[dict]:
    """Прочитать глоссарий. Если JSON нет — отдать только ручные `short` (фолбэк)."""
    global _cache
    if _cache is not None:
        return _cache
    p = _path(cfg)
    if p.exists():
        _cache = json.loads(p.read_text(encoding="utf-8"))
    else:
        _cache = [{"term": t, "short": s, "enc": "", "source": ""} for t, s in GLOSSARY_SEED]
    return _cache


def search(cfg: dict, q: str, limit: int = 30) -> list[dict]:
    """Подстрочный поиск по термину (мгновенно, без LLM)."""
    q = (q or "").strip().lower()
    items = load(cfg)
    if not q:
        return items[:limit]
    ranked = []
    for it in items:
        t = it["term"].lower()
        if t == q:
            ranked.append((0, it))
        elif t.startswith(q):
            ranked.append((1, it))
        elif q in t or q in it["short"].lower() or q in it.get("enc", "").lower():
            ranked.append((2, it))
    ranked.sort(key=lambda x: x[0])
    return [it for _, it in ranked[:limit]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true", help="собрать glossary.json из индекса")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    cfg = config.load(args.config)
    if args.build:
        build(cfg)
    else:
        for it in load(cfg):
            print(f"- {it['term']}: {it['enc'] or it['short']}")


if __name__ == "__main__":
    main()
