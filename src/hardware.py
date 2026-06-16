"""Проверка железа машины — для авто-оптимизации параметров LLM.

detect() возвращает CPU/RAM/GPU. На этой машине: Intel Arc (без CUDA) → LLM крутится
через Vulkan в LM Studio, эмбеддинги/Whisper на CPU. Результат кэшируется.
"""
import platform
import subprocess

_cache = None


def _gpus() -> list[str]:
    """Имена видеокарт (Windows, через CIM). Пусто при ошибке."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=15)
        return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    except (subprocess.SubprocessError, OSError):
        return []


def detect() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    cores = ram_gb = 0
    try:
        import psutil
        cores = psutil.cpu_count(logical=True) or 0
        ram_gb = round(psutil.virtual_memory().total / 1e9, 1)
    except Exception:  # noqa: BLE001
        pass
    gpus = _gpus()
    g = " ".join(gpus).lower()
    vendor = ("nvidia" if "nvidia" in g or "geforce" in g or "rtx" in g else
              "amd" if "radeon" in g or "amd" in g else
              "intel" if "intel" in g or "arc" in g else "unknown")
    _cache = {
        "cpu": platform.processor() or "?",
        "cores": cores,
        "ram_gb": ram_gb,
        "gpus": gpus,
        "gpu_vendor": vendor,
        "has_cuda": vendor == "nvidia",   # только nvidia = CUDA-ускорение эмбеддингов/whisper
    }
    return _cache


def summary() -> str:
    h = detect()
    gpu = ", ".join(h["gpus"]) or "—"
    return (f"CPU {h['cores']} ядер · RAM {h['ram_gb']} ГБ · GPU {gpu} "
            f"({h['gpu_vendor']}, CUDA: {'да' if h['has_cuda'] else 'нет'})")
