"""Клиент LM Studio (OpenAI-совместимый /v1/chat/completions)."""
import json
import requests


def is_up(base_url: str) -> bool:
    try:
        requests.get(f"{base_url}/models", timeout=3)
        return True
    except requests.RequestException:
        return False


def list_models(base_url: str) -> list[str]:
    r = requests.get(f"{base_url}/models", timeout=5)
    r.raise_for_status()
    return [m["id"] for m in r.json().get("data", [])]


def _native_base(base_url: str) -> str:
    # "http://localhost:1234/v1" -> "http://localhost:1234"
    return base_url.rstrip("/")[:-3].rstrip("/") if base_url.rstrip("/").endswith("/v1") else base_url.rstrip("/")


def all_models(base_url: str) -> list[dict]:
    """ВСЕ модели одним запросом к нативному /api/v0/models (вызов LM Studio ~2с —
    дёргать редко!). Отсюда деривируются и загруженные, и метаданные — без лишних HTTP."""
    try:
        r = requests.get(f"{_native_base(base_url)}/api/v0/models", timeout=5)
        r.raise_for_status()
        return r.json().get("data", [])
    except (requests.RequestException, ValueError, KeyError):
        return []


def loaded_llms(base_url: str) -> list[str]:
    """id моделей, реально ЗАГРУЖЕННЫХ в LM Studio (через нативный /api/v0/models),
    без embedding-моделей. Пусто, если нативный API недоступен."""
    try:
        r = requests.get(f"{_native_base(base_url)}/api/v0/models", timeout=5)
        r.raise_for_status()
        out = []
        for m in r.json().get("data", []):
            if m.get("state") == "loaded" and m.get("type") not in ("embeddings", "embedding"):
                out.append(m["id"])
        return out
    except (requests.RequestException, ValueError, KeyError):
        return []


def model_meta(base_url: str, model_id: str) -> dict:
    """Метаданные модели из нативного API LM Studio: arch, quantization,
    loaded_context_length (реальный n_ctx), max_context_length, capabilities.
    Пусто, если API недоступен или модель не найдена."""
    try:
        r = requests.get(f"{_native_base(base_url)}/api/v0/models", timeout=5)
        r.raise_for_status()
        for m in r.json().get("data", []):
            if m.get("id") == model_id:
                return m
    except (requests.RequestException, ValueError, KeyError):
        pass
    return {}


def looks_reasoning(model_id: str) -> bool:
    m = model_id.lower()
    return any(k in m for k in ("gemma-4", "qwq", "deepseek-r1", "-r1", "reason", "thinking"))


# Минимум токенов для reasoning-моделей: скрытые размышления съедают бюджет,
# при малом лимите ответ (content) не успевает выйти. Гарантируем запас.
REASONING_MIN_TOKENS = 3000


def _reasoning_off(cfg_lm: dict) -> bool:
    """reasoning_effort: none/off/low — размышления выключены (LM Studio это понимает)."""
    return str(cfg_lm.get("reasoning_effort", "")).lower() in ("none", "off", "false", "low")


def _effective_max_tokens(cfg_lm: dict) -> int:
    mt = cfg_lm.get("max_tokens", 1024)
    # форсим запас только если reasoning реально работает (иначе он съест бюджет)
    if looks_reasoning(cfg_lm.get("model", "")) and not _reasoning_off(cfg_lm):
        return max(mt, REASONING_MIN_TOKENS)
    return mt


def _with_reasoning(payload: dict, cfg_lm: dict) -> dict:
    """Прокинуть reasoning_effort в запрос (none/low/medium/high)."""
    eff = cfg_lm.get("reasoning_effort")
    if eff:
        payload["reasoning_effort"] = eff
    return payload


def resolve_model(cfg_lm: dict) -> str:
    """Какую модель реально использовать.
    1) если модель из config загружена — берём её;
    2) иначе берём любую загруженную LLM (авто-подхват);
    3) иначе оставляем из config (LM Studio подгрузит по JIT)."""
    want = cfg_lm.get("model", "")
    loaded = loaded_llms(cfg_lm["base_url"])
    if want in loaded:
        return want
    if loaded:
        return loaded[0]
    return want


def stream_deltas(cfg_lm: dict, messages: list[dict]):
    """Генератор для web/SSE. Выдаёт ('think', txt) для скрытых размышлений
    reasoning-моделей и ('content', txt) для самого ответа — UI показывает
    «думает» вживую, чтобы не было мёртвой тишины на 20-30 с."""
    url = f"{cfg_lm['base_url']}/chat/completions"
    payload = _with_reasoning({
        "model": cfg_lm["model"],
        "messages": messages,
        "temperature": cfg_lm.get("temperature", 0.2),
        "max_tokens": _effective_max_tokens(cfg_lm),
        "stream": True,
    }, cfg_lm)
    with requests.post(url, json=payload, stream=True, timeout=600) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            s = line.decode("utf-8")
            if s.startswith("data: "):
                s = s[6:]
            if s.strip() == "[DONE]":
                break
            try:
                d = json.loads(s)["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            content = d.get("content") or ""
            if content:
                yield ("content", content)
                continue
            think = d.get("reasoning_content") or d.get("reasoning") or ""
            if think:
                yield ("think", think)


def chat(cfg_lm: dict, messages: list[dict], stream: bool = True) -> str:
    url = f"{cfg_lm['base_url']}/chat/completions"
    payload = _with_reasoning({
        "model": cfg_lm["model"],
        "messages": messages,
        "temperature": cfg_lm.get("temperature", 0.2),
        "max_tokens": _effective_max_tokens(cfg_lm),
        "stream": stream,
    }, cfg_lm)
    if not stream:
        r = requests.post(url, json=payload, timeout=600)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    out = []
    with requests.post(url, json=payload, stream=True, timeout=600) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            s = line.decode("utf-8")
            if s.startswith("data: "):
                s = s[6:]
            if s.strip() == "[DONE]":
                break
            try:
                d = json.loads(s)["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            delta = d.get("content") or ""
            # reasoning-модели (gemma-4-*) шлют размышления отдельным полем;
            # показываем точку прогресса, в ответ не подмешиваем.
            if not delta and (d.get("reasoning_content") or d.get("reasoning")):
                print(".", end="", flush=True)
                continue
            if delta:
                print(delta, end="", flush=True)
                out.append(delta)
    print()
    return "".join(out)
