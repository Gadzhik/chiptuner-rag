"""Загрузка config.yaml."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent


def load(path: str | None = None) -> dict:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_root"] = str(ROOT)
    return cfg
