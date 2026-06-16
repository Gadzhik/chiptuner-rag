"""Авто-оптимизация LLM под железо и реально загруженную в LM Studio модель.

Программа НЕ управляет загрузкой модели (n_ctx/GPU-слои задаются при загрузке в
LM Studio), но per-request управляет тем, что даёт максимум производительности и
полноты ответа, и подгоняет это под фактический контекст модели:

  • reasoning_effort = none  — выключить скрытые размышления (быстрее всего);
  • max_tokens               — максимум под размер контекста (ответ не обрежется);
  • max_context_chars        — бюджет RAG-контекста, чтобы промпт влез в n_ctx
                               (иначе ошибка LM Studio "tokens to keep > n_ctx").

`ensure_optimized(cfg)` вызывается при старте И перед каждым запросом: если в
LM Studio сменили модель — параметры пересчитываются автоматически.
"""
import threading
import time

from . import hardware, lmstudio

CHARS_PER_TOKEN = 1.25     # русский токенизируется тяжело; занижаем (не переполнить n_ctx)
OVERHEAD_TOKENS = 600      # system-prompt + обвязка + вопрос (с запасом)

# Потолки ЗАВИСЯТ ОТ ЖЕЛЕЗА. На GPU без CUDA (Intel Arc/AMD) и на CPU prefill промпта
# ОЧЕНЬ медленный (~1 с на 120 символов на Arc): большой контекст = минута тишины до
# первого токена. Поэтому там промпт держим маленьким ради отзывчивости. На CUDA prefill
# быстрый — можно набивать контекст для полноты.
#                  (max_tokens, ctx_chars, top_k)
CAPS_CUDA   = (2048, 24000, 12)   # nvidia: prefill быстрый, контекст не жалко
CAPS_NOCUDA = (1100,  3800,  5)   # Arc/AMD/CPU: маленький промпт = быстрый ответ

RECHECK_TTL = 25.0         # путь запроса в пределах TTL не дёргает LM Studio (API ~2с/вызов)
BG_INTERVAL = 15.0         # фоновый поток обновляет настройки чаще TTL — кэш всегда «тёплый»

_state = {"model": None, "n_ctx": None, "report": "", "t": 0.0}


def _plan(n_ctx: int, chunk_chars: int, has_cuda: bool) -> dict:
    """Оптимальные max_tokens, бюджет контекста и top_k под окно модели И железо."""
    tok_cap, ctx_cap, topk_cap = CAPS_CUDA if has_cuda else CAPS_NOCUDA
    max_tokens = min(max(512, n_ctx // 4), tok_cap)
    input_tokens = max(256, n_ctx - max_tokens - OVERHEAD_TOKENS)
    ctx_chars = max(800, min(int(input_tokens * CHARS_PER_TOKEN), ctx_cap))
    top_k = max(3, min(ctx_chars // max(chunk_chars, 1), topk_cap))
    return {"max_tokens": max_tokens, "max_context_chars": ctx_chars, "top_k": top_k}


def ensure_optimized(cfg: dict, verbose: bool = False) -> str:
    """Подобрать и применить оптимальные настройки. Пересчитывает при смене модели.

    Кэшируется: внутри RECHECK_TTL секунд НЕ дёргает LM Studio (его API ~2с/вызов) —
    иначе каждый вопрос тормозил бы на ~6с. Один запрос /api/v0/models на проверку."""
    lm = cfg["lmstudio"]
    base = lm["base_url"]
    now = time.time()

    # свежая проверка недавно была — отдаём кэш, без HTTP
    if _state["model"] and now - _state["t"] < RECHECK_TTL:
        lm["model"] = _state["model"]
        return _state["report"]

    data = lmstudio.all_models(base)                       # ЕДИНСТВЕННЫЙ вызов
    _state["t"] = now
    if not data:
        return _state["report"] or "LM Studio не отвечает."

    loaded = [m["id"] for m in data
              if m.get("state") == "loaded" and m.get("type") not in ("embeddings", "embedding")]
    want = lm.get("model", "")
    chosen = want if want in loaded else (loaded[0] if loaded else want)
    meta = next((m for m in data if m.get("id") == chosen), {})
    n_ctx = int(meta.get("loaded_context_length") or 0) or 4096

    # пересчитывать только если сменилась модель или её контекст
    if chosen == _state["model"] and n_ctx == _state["n_ctx"]:
        lm["model"] = chosen
        return _state["report"]

    h = hardware.detect()
    reasoning = lmstudio.looks_reasoning(chosen)
    plan = _plan(n_ctx, cfg.get("chunk_chars", 1200), h["has_cuda"])
    lm["model"] = chosen
    # reasoning_effort шлём ТОЛЬКО reasoning-моделям (иначе LM Studio пишет в лог
    # "overrides reasoning metadata ... skipping" — безвредно, но шум).
    lm["reasoning_effort"] = "none" if reasoning else ""
    lm["max_tokens"] = plan["max_tokens"]
    cfg["max_context_chars"] = plan["max_context_chars"]
    cfg["top_k"] = plan["top_k"]
    quant = meta.get("quantization", "?")
    arch = meta.get("arch", "?")
    report = (
        f"Модель: {chosen} [{arch}, {quant}]\n"
        f"  железо: {hardware.summary()}\n"
        f"  контекст модели (n_ctx): {n_ctx}"
        + (f" (модель поддерживает до {meta.get('max_context_length')})"
           if meta.get("max_context_length") else "") + "\n"
        f"  оптимизация: reasoning=OFF, max_tokens={plan['max_tokens']}, "
        f"context_chars={plan['max_context_chars']}, top_k={plan['top_k']}"
        + (" · ⚠ reasoning-модель: размышления отключены для скорости" if reasoning else "")
    )
    if h["has_cuda"]:
        report += "\n  🚀 CUDA: prefill быстрый — контекст набивается для полноты ответов."
    else:
        report += ("\n  🐢 без CUDA (Intel Arc/AMD/CPU): prefill промпта медленный, поэтому "
                   "контекст держим маленьким ради отзывчивости (быстрый первый токен). "
                   "Поднимать n_ctx модели смысла нет — упор в скорость железа, не в окно.")

    _state.update(model=chosen, n_ctx=n_ctx, report=report)
    if verbose:
        print(report)
    return report


def start_background(cfg: dict, interval: float = BG_INTERVAL) -> None:
    """Фоновый демон-поток: периодически переоптимизирует cfg (тот же объект, что у web),
    чтобы путь запроса НИКОГДА не ждал медленный API LM Studio. Смена модели в LM Studio
    подхватывается за ~interval секунд автоматически."""
    def loop():
        while True:
            try:
                ensure_optimized(cfg)
            except Exception:  # noqa: BLE001 — фон не должен падать
                pass
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True, name="opt-refresh").start()
