# processors/dedupe.py
from __future__ import annotations
from utils.logger import setup_logging

logger = setup_logging("dedupe")

def is_duplicate(post_text: str, recent_posts: list, content_key: str = "") -> bool:
    """Check if a post is a duplicate based on content_key or exact text."""
    if not post_text and not content_key:
        return False
    text_norm = " ".join((post_text or "").lower().split())
    key_norm  = " ".join((content_key or "").lower().split())
    for row in recent_posts:
        if key_norm and key_norm == " ".join((row.get("content_key","") or "").lower().split()):
            logger.debug("Duplicate via content_key")
            return True
        if text_norm and text_norm == " ".join((row.get("post_text","") or "").lower().split()):
            logger.debug("Duplicate via text match")
            return True
    return False
