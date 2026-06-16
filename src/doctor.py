"""Проверка окружения: зависимости, LM Studio, индекс, папки."""
from pathlib import Path

from . import config, lmstudio


def main():
    print("=== ChipTuner Assistant — проверка ===")
    cfg = config.load()

    # 1. зависимости
    for mod in ("chromadb", "sentence_transformers", "fitz", "requests", "yaml"):
        try:
            __import__(mod)
            print(f"[ok]  модуль {mod}")
        except ImportError:
            print(f"[!!]  НЕТ модуля {mod} -> pip install -r requirements.txt")

    # 2. папки с документами
    for d in cfg["docs_dirs"]:
        p = Path(d)
        if p.exists():
            cnt = sum(1 for _ in p.rglob("*") if _.is_file())
            print(f"[ok]  docs: {d}  ({cnt} файлов)")
        else:
            print(f"[!!]  НЕТ папки docs: {d}  (распакуй сюда свои документы)")

    # 3. LM Studio
    lm = cfg["lmstudio"]
    if lmstudio.is_up(lm["base_url"]):
        models = lmstudio.list_models(lm["base_url"])
        print(f"[ok]  LM Studio на {lm['base_url']}; модели: {', '.join(models) or '(нет)'}")
        if lm["model"] not in models:
            print(f"[??]  модель из config '{lm['model']}' не в списке загруженных")
    else:
        print(f"[!!]  LM Studio не отвечает на {lm['base_url']} -> Developer -> Start Server")

    # 4. индекс
    chroma = Path(cfg["data_dir"]) / "chroma"
    print(f"[..]  индекс {'есть' if chroma.exists() else 'НЕ создан (запусти ingest)'}: {chroma}")


if __name__ == "__main__":
    main()
