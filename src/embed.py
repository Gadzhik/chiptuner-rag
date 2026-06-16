"""Embeddings через sentence-transformers (multilingual-e5, CPU).

e5 требует префиксы: "query: " для вопроса, "passage: " для документа.
"""
from sentence_transformers import SentenceTransformer

_model = None
_name = None


def _get(model_name: str) -> SentenceTransformer:
    global _model, _name
    if _model is None or _name != model_name:
        print(f"[embed] загрузка модели {model_name} (CPU)...")
        _model = SentenceTransformer(model_name, device="cpu")
        _name = model_name
    return _model


def embed_passages(model_name: str, texts: list[str]) -> list[list[float]]:
    m = _get(model_name)
    inp = [f"passage: {t}" for t in texts]
    return m.encode(inp, normalize_embeddings=True, show_progress_bar=False).tolist()


def embed_query(model_name: str, text: str) -> list[float]:
    m = _get(model_name)
    v = m.encode([f"query: {text}"], normalize_embeddings=True)[0]
    return v.tolist()
