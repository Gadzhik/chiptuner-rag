"""Извлечение текста из разных форматов документов.

Поддержка: .pdf .txt .md .docx .rtf .htm/.html .xlsx
PDF: сначала текстовый слой; если пусто (скан) — помечаем как требующий OCR (пока пропуск).
"""
from pathlib import Path

SUPPORTED = {".pdf", ".txt", ".md", ".docx", ".rtf", ".htm", ".html", ".xlsx"}


def extract(path: Path) -> str:
    ext = path.suffix.lower()
    try:
        if ext == ".pdf":
            return _pdf(path)
        if ext in {".txt", ".md"}:
            return _plain(path)
        if ext == ".docx":
            return _docx(path)
        if ext == ".rtf":
            return _rtf(path)
        if ext in {".htm", ".html"}:
            return _html(path)
        if ext == ".xlsx":
            return _xlsx(path)
    except Exception as e:  # noqa: BLE001
        print(f"  ! ошибка чтения {path.name}: {e}")
    return ""


def _plain(path: Path) -> str:
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", "replace")


def _pdf(path: Path) -> str:
    import fitz
    parts = []
    with fitz.open(path) as doc:
        for page in doc:
            parts.append(page.get_text())
    text = "\n".join(parts)
    # Скан без текстового слоя -> пусто. OCR добавим отдельным модулем.
    return text


def _docx(path: Path) -> str:
    import docx
    d = docx.Document(str(path))
    return "\n".join(p.text for p in d.paragraphs)


def _rtf(path: Path) -> str:
    from striprtf.striprtf import rtf_to_text
    return rtf_to_text(_plain(path))


def _html(path: Path) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(_plain(path), "html.parser")
    return soup.get_text("\n")


def _xlsx(path: Path) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    rows = []
    for ws in wb.worksheets:
        rows.append(f"# Лист: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                rows.append("\t".join(cells))
    return "\n".join(rows)
