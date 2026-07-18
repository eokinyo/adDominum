# processors/formatter.py
from __future__ import annotations
import re
from pathlib import Path
from typing import Any
from utils.logger import setup_logging
from utils.card_maker import make_card_for_item

logger = setup_logging("formatter")
MAX_POST_LENGTH = 280


def clean(text: str) -> str:
    text = " ".join(str(text or "").split()).strip()
    # Strip trailing attribution artifacts e.g. text"- or text"-
    text = re.sub(r'[\u201c\u201d\u2018\u2019"\']+[\u2013\u2014\-]+\s*$', '', text).strip()
    return text


def teaser(text: str, max_chars: int = 220) -> str:
    """
    Return a meaningful excerpt.
    - Fits entirely -> use all of it
    - Too long -> sentence boundary only if >= 60 chars
    - Fallback -> word boundary near limit
    """
    text = clean(text)
    if len(text) <= max_chars:
        return text
    for punct in (".", "!", "?"):
        idx = text.find(punct)
        if 60 < idx <= max_chars:
            return text[:idx + 1]
    truncated = text[:max_chars].rsplit(" ", 1)[0].rstrip(".,;:\u2014")
    return truncated + "\u2026"


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    for punct in (".", "!", "?"):
        idx = text.rfind(punct, 0, max_chars - 1)
        if idx > max_chars // 2:
            return text[:idx + 1]
    return text[:max_chars - 1].rsplit(" ", 1)[0].rstrip(".,;:") + "\u2026"


def _quote_text(item: dict) -> str:
    quote   = clean(item.get("quote", ""))
    author  = clean(item.get("author", ""))
    excerpt = teaser(quote, 220)
    body = f'"{excerpt}"\n\n\u2014 {author}' if author and author != "Unknown" else f'"{excerpt}"'
    return truncate(body, MAX_POST_LENGTH)


def _benedict_text(item: dict) -> str:
    quote   = clean(item.get("quote", ""))
    excerpt = teaser(quote, 220)
    return truncate(f'Pope Benedict XVI\n\n"{excerpt}"', MAX_POST_LENGTH)


def _history_text(item: dict) -> str:
    summary = clean(item.get("summary", ""))
    excerpt = teaser(summary, 220)
    try:
        m  = int(item.get("month", 0))
        d  = int(item.get("day", 0))
        y  = int(item.get("year", 0))
        mn = ["","January","February","March","April","May","June",
              "July","August","September","October","November","December"]
        date_line = f"\U0001f4c5 {d} {mn[m]} {y}" if y else f"\U0001f4c5 {d} {mn[m]}"
    except Exception:
        date_line = "\U0001f4c5 Church History"
    return truncate(f"{date_line}\n\n{excerpt}", MAX_POST_LENGTH)


def format_post(item: dict[str, Any]) -> dict[str, Any]:
    if not item:
        return {"text": "", "card_path": None}
    dataset     = str(item.get("dataset", "")).lower()
    source_type = str(item.get("source_type", "quote")).lower()
    topic       = str(item.get("topic", "")).lower()
    try:
        if dataset == "benedict" or topic == "benedict":
            text = _benedict_text(item)
        elif dataset == "church_history" or source_type == "history":
            text = _history_text(item)
        else:
            text = _quote_text(item)
        card_path = make_card_for_item(item)
        logger.info(f"Formatted | {len(text)} chars | card: {card_path.name if card_path else 'none'}")
        return {"text": text, "card_path": card_path}
    except Exception as e:
        logger.error(f"format_post failed: {e}")
        fallback = clean(item.get("quote") or item.get("summary") or "")
        return {"text": fallback[:MAX_POST_LENGTH], "card_path": None}
