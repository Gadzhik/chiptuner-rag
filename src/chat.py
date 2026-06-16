"""Интерактивный чат-бот по справочникам.

Запуск:
    python -m src.chat
Команды внутри: /quit выход, /src показать источники последнего ответа.
"""
from . import config, lmstudio, optimize, rag


def main():
    cfg = config.load()
    lm = cfg["lmstudio"]

    if not lmstudio.is_up(lm["base_url"]):
        print(f"! LM Studio не отвечает на {lm['base_url']}")
        print("  Открой LM Studio -> вкладка Developer -> Start Server (порт 1234).")
        print("  И загрузи модель:", lm["model"])
        return

    print(optimize.ensure_optimized(cfg, verbose=False))

    col = rag.get_collection(cfg)
    n = col.count()
    if n == 0:
        print("! Индекс пуст. Сначала: python -m src.ingest")
        return
    print(f"Готово. В индексе {n} фрагментов. Спрашивай (/quit — выход).\n")

    last = None
    while True:
        try:
            q = input("Ты> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q == "/quit":
            break
        if q == "/src":
            if last:
                for s in last["sources"]:
                    print(f"  - {s['name']}  (score {s['score']})  {s['path']}")
            continue
        if q == "/files":
            if last:
                for f in last.get("files", []):
                    print(f"  [{f['size']/1e6:7.1f} MB] {f['path']}")
                    print(f"            архив: {f['archive']}")
            continue
        optimize.ensure_optimized(cfg)   # вдруг сменили модель в LM Studio
        print("ИИ> ", end="", flush=True)
        last = rag.answer(cfg, col, q, stream=True)
        print("Источники:", ", ".join(s["name"] for s in last["sources"]))
        files = last.get("files", [])
        if files:
            print(f"\nФайлы в архиве по теме ({len(files)}):")
            for f in files[:8]:
                tag = f"{f['ecu'] or f['brand'] or f['category']}"
                print(f"  [{f['size']/1e6:7.1f} MB] {tag:18} {f['path']}")
        print()


if __name__ == "__main__":
    main()
