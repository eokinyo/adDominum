# publishing/papal_feed.py
"""
adDominum — Papal Feed

Fetches the Pope's Wednesday General Audience or Sunday Angelus
and posts a clean summary to X.

Run manually or via Task Scheduler:
    python publishing/papal_feed.py           # dry run
    python publishing/papal_feed.py --live    # post to X
    python publishing/papal_feed.py --force   # ignore duplicate check

Strategy (in order):
  1. Build Vatican.va URL from today's date and fetch directly
  2. Search OSV News RSS for audience/Angelus article
  3. Search Zenit RSS
  4. Search Catholic News Agency RSS
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

try:
    import feedparser
    import requests
except ImportError:
    print("Run: pip install feedparser requests")
    sys.exit(1)

from utils.logger import setup_logging
from utils.config import config
from utils.card_maker import make_card
from publishing.poster import Poster

logger = setup_logging("papal_feed")

# =========================================================
# RSS SOURCES
# =========================================================
RSS_SOURCES = [
    "https://www.osvnews.com/feed/",
    "https://www.osvnews.com/category/pope/feed/",
    "https://zenit.org/feed/",
    "https://www.catholicnewsagency.com/feed",
    "https://cruxnow.com/feed/",
    "https://www.ncregister.com/rss/rss.json",
]

# Broader keyword set — catches more article types
TEACHING_KEYWORDS = [
    "general audience", "wednesday audience", "catechesis", "catechetical",
    "angelus", "regina coeli", "sunday address", "urbi et orbi",
    "apostolic journey", "homily", "address to", "papal message",
    "leo xiv", "pope leo", "holy father", "pontiff says", "pope says",
    "audience", "reflection", "meditation", "weekly address",
]

SKIP_KEYWORDS = [
    "obituary", "died", "appointment", "resignation",
    "financial report", "administration", "salary",
]

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# How old an RSS item may be before it is considered stale
MAX_ENTRY_AGE_DAYS = 10

# =========================================================
# POST LOG
# =========================================================
PAPAL_LOG = BASE_DIR / "logs" / "papal_log.csv"


def load_papal_log() -> set[str]:
    if not PAPAL_LOG.exists():
        return set()
    posted = set()
    try:
        with PAPAL_LOG.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                posted.add(row.get("url", ""))
    except Exception as e:
        logger.warning(f"Could not read papal log: {e}")
    return posted


def save_papal_log(url: str, title: str) -> None:
    write_header = not PAPAL_LOG.exists()
    PAPAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with PAPAL_LOG.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "url", "title"])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(), url, title
        ])


# =========================================================
# DATE HELPERS
# =========================================================
def last_wednesday() -> date:
    """Return the most recent Wednesday (today if Wednesday)."""
    today = date.today()
    days_since_wed = (today.weekday() - 2) % 7
    return today - timedelta(days=days_since_wed)


def last_sunday() -> date:
    """Return the most recent Sunday (today if Sunday)."""
    today = date.today()
    days_since_sun = (today.weekday() - 6) % 7
    return today - timedelta(days=days_since_sun)


# =========================================================
# TEXT EXTRACTION
# =========================================================
def clean_page_text(raw_bytes: bytes) -> str:
    """Decode page bytes properly and strip HTML."""
    # Force UTF-8 to avoid curly quote mangling
    try:
        html = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        html = raw_bytes.decode("latin-1", errors="replace")

    # Strip scripts and styles
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html,
                  flags=re.DOTALL | re.IGNORECASE)

    # Strip all HTML tags
    text = re.sub(r"<[^>]+>", " ", html)

    # Decode HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&#160;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&quot;", '"')
    text = text.replace("&apos;", "'")
    text = text.replace("&#39;", "'")

    # Normalise smart quotes and dashes to plain ASCII for reliable matching
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_html(raw: str) -> str:
    """Strip HTML tags and entities from an RSS summary field."""
    if not raw:
        return ""

    text = re.sub(r"<script[^>]*>.*?</script>", " ", raw,
                  flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text,
                  flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)

    replacements = {
        "&nbsp;": " ", "&#160;": " ", "&amp;": "&", "&quot;": '"',
        "&apos;": "'", "&#39;": "'", "&lt;": "<", "&gt;": ">",
        "&hellip;": "...", "&mdash;": "-", "&ndash;": "-",
        "&rsquo;": "'", "&lsquo;": "'", "&ldquo;": '"', "&rdquo;": '"',
    }
    for entity, char in replacements.items():
        text = text.replace(entity, char)

    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-")

    return re.sub(r"\s+", " ", text).strip()


# Only explicit, unambiguous headings. A bare "Summary:" or "SUMMARY" would
# match navigation, cookie banners, or sidebar text and post it as the
# Holy Father's words.
SUMMARY_PATTERNS = [
    r"Summary of the Holy Father['\u2019]s words:?",
    r"Summary of the Pope['\u2019]s words:?",
]

SUMMARY_STOP_MARKERS = [
    "Copyright", "Dicastery for Communication", "Libreria Editrice",
    "___", "* * *", "APPEALS", "All rights reserved",
]


def extract_vatican_summary(page_text: str) -> str:
    """
    Extract the Vatican's official summary from an audience page.

    Vatican.va ends every General Audience with a pre-written English
    summary under the heading "Summary of the Holy Father's words:".
    That text is clean, short, and written for exactly this purpose.
    Returns "" if no such heading is present.
    """
    for pattern in SUMMARY_PATTERNS:
        match = re.search(pattern, page_text, flags=re.IGNORECASE)
        if not match:
            continue

        after = page_text[match.end():].strip()

        # Remove the standard opener
        after = re.sub(r"^Dear brothers and sisters,?\s*", "", after).strip()

        # Cut at whatever end-of-content marker comes first
        cut = len(after)
        for stop in SUMMARY_STOP_MARKERS:
            stop_idx = after.find(stop)
            if 0 < stop_idx < cut:
                cut = stop_idx
        after = after[:cut].strip()

        after = re.sub(r"\s+", " ", after).strip()
        if len(after) > 80:
            return after

    return ""


def extract_best_passage(full_text: str, max_chars: int = 500) -> str:
    """
    Skip the greeting and find the actual theological/pastoral core.
    """
    substance_markers = [
        "i want to", "i wish to", "we must", "the church", "christ",
        "god calls", "faith teaches", "the council", "the gospel",
        "let us", "i would like to invite", "this encounter",
        "it is a heritage", "the rites", "in the liturgy",
        "the holy spirit", "the word of god", "our faith",
        "the christian", "we are called", "tradition",
    ]

    # Split into sentences
    sentences, current = [], ""
    for char in full_text:
        current += char
        if char in ".!?" and len(current) > 20:
            sentences.append(current.strip())
            current = ""
    if current.strip():
        sentences.append(current.strip())

    if not sentences:
        return ""

    # Skip greeting sentences
    skip = 0
    for i, s in enumerate(sentences[:3]):
        sl = s.lower()
        if any(w in sl for w in
               ["good morning", "welcome", "today i would", "today, i would"]):
            skip = i + 1

    remaining = sentences[skip:]
    if not remaining:
        remaining = sentences

    # Find first sentence with substance
    start = 0
    for i, s in enumerate(remaining):
        if any(m in s.lower() for m in substance_markers):
            start = i
            break

    # Build passage
    passage = ""
    for s in remaining[start:]:
        if len(passage) + len(s) + 1 > max_chars:
            break
        passage += (" " if passage else "") + s

    return passage.strip() if passage else " ".join(remaining[:3])


# =========================================================
# STRATEGY 1: DIRECT VATICAN.VA URL
# =========================================================
def try_vatican_direct(posted_urls: set[str] | None = None) -> dict | None:
    """
    Fetch directly from Vatican.va using the known audience URL pattern.
    Tries today (if Wed/Sun), then last Wednesday and last Sunday.

    Candidates already present in the papal log are skipped, so a stale
    Wednesday audience no longer blocks the RSS fallback on a Sunday.
    """
    posted_urls = posted_urls or set()
    today   = date.today()
    weekday = today.weekday()

    candidates = []

    if weekday == 2:   # Wednesday
        candidates.append((
            f"https://www.vatican.va/content/leo-xiv/en/audiences/"
            f"{today.year}/documents/{today.strftime('%Y%m%d')}"
            f"-udienza-generale.html",
            "General Audience"
        ))
    elif weekday == 6:  # Sunday
        candidates.append((
            f"https://www.vatican.va/content/leo-xiv/en/angelus/"
            f"{today.year}/documents/{today.strftime('%Y%m%d')}"
            f"-angelus.html",
            "Angelus"
        ))

    # Always add recent Wed and Sun as fallbacks
    wed = last_wednesday()
    sun = last_sunday()
    candidates += [
        (
            f"https://www.vatican.va/content/leo-xiv/en/audiences/"
            f"{wed.year}/documents/{wed.strftime('%Y%m%d')}"
            f"-udienza-generale.html",
            "General Audience"
        ),
        (
            f"https://www.vatican.va/content/leo-xiv/en/angelus/"
            f"{sun.year}/documents/{sun.strftime('%Y%m%d')}"
            f"-angelus.html",
            "Angelus"
        ),
    ]

    # De-duplicate while preserving order (today's URL may repeat the fallback)
    seen = set()
    unique_candidates = []
    for url, label in candidates:
        if url not in seen:
            seen.add(url)
            unique_candidates.append((url, label))

    for url, type_label in unique_candidates:
        if url in posted_urls:
            logger.debug(f"Vatican.va candidate already posted: {url}")
            continue

        try:
            r = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
            if r.status_code != 200:
                logger.debug(f"Vatican.va {r.status_code}: {url}")
                continue

            # Use raw bytes and force UTF-8 decode
            text = clean_page_text(r.content)

            # Try to get the official Vatican summary first
            excerpt = extract_vatican_summary(text)

            # Fall back to extract_best_passage if no summary found
            if not excerpt:
                logger.debug("No summary section found, using passage extraction")
                for opener in ["Dear brothers and sisters", "Dear friends",
                               "Good morning", "Brothers and sisters"]:
                    idx = text.find(opener)
                    if idx > 0:
                        raw = text[idx:idx + 2000]
                        excerpt = extract_best_passage(raw)
                        break

            if not excerpt:
                logger.warning(f"No excerpt found in {url}")
                continue

            logger.info(f"Vatican.va direct fetch succeeded: {type_label}")
            logger.info(f"Summary ({len(excerpt)} chars): {excerpt[:150]}...")
            return {
                "title":   f"Pope Leo XIV - {type_label}",
                "url":     url,
                "summary": excerpt,
                "type":    type_label,
            }

        except Exception as e:
            logger.debug(f"Vatican.va error ({url}): {e}")
            continue

    return None


# =========================================================
# STRATEGY 2: RSS FALLBACK
# =========================================================
def fetch_feed(rss_url: str) -> list:
    """
    Fetch and parse one RSS feed. Returns a list of entries, or an empty
    list on any failure — a dead feed must never take the run down.
    """
    try:
        r = requests.get(rss_url, headers=REQUEST_HEADERS, timeout=20)
        if r.status_code != 200:
            logger.debug(f"Feed {r.status_code}: {rss_url}")
            return []

        parsed = feedparser.parse(r.content)
        entries = parsed.get("entries", []) or []
        logger.debug(f"Feed OK ({len(entries)} entries): {rss_url}")
        return entries

    except Exception as e:
        logger.debug(f"Feed error ({rss_url}): {e}")
        return []


def is_teaching(entry: dict) -> bool:
    """
    Decide whether an RSS entry is papal teaching worth posting.

    Requires a TEACHING_KEYWORDS hit and no SKIP_KEYWORDS hit. Only the
    title and summary are checked — the full article is not fetched until
    an entry has already passed this filter.
    """
    title   = (entry.get("title") or "").lower()
    summary = clean_html(entry.get("summary") or "").lower()
    haystack = f"{title} {summary}"

    if any(skip in haystack for skip in SKIP_KEYWORDS):
        logger.debug(f"Skipped (skip keyword): {title[:60]}")
        return False

    if not any(kw in haystack for kw in TEACHING_KEYWORDS):
        return False

    # Feeds can carry months of archive — an Angelus from March is not news.
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if published:
        try:
            entry_date = date(published.tm_year, published.tm_mon,
                              published.tm_mday)
            age_days = (date.today() - entry_date).days
            if age_days > MAX_ENTRY_AGE_DAYS:
                logger.debug(f"Skipped ({age_days} days old): {title[:60]}")
                return False
        except Exception:
            pass  # Malformed date — let it through on keywords alone

    return True


def fetch_article_excerpt(url: str, max_chars: int = 600) -> str:
    """
    Fetch a news article and pull a readable excerpt from it.
    Returns "" on failure so the caller can fall back to the RSS summary.
    """
    if not url:
        return ""

    try:
        r = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
        if r.status_code != 200:
            logger.debug(f"Article {r.status_code}: {url}")
            return ""

        text = clean_page_text(r.content)

        # Drop boilerplate that precedes the article body on most sites
        for opener in ["Dear brothers and sisters", "Dear friends",
                       "Good morning", "Brothers and sisters",
                       "VATICAN CITY", "ROME"]:
            idx = text.find(opener)
            if idx > 0:
                text = text[idx:]
                break

        if len(text) < 100:
            return ""

        return extract_best_passage(text[:4000], max_chars=max_chars)

    except Exception as e:
        logger.debug(f"Article fetch error ({url}): {e}")
        return ""


def try_rss_sources(posted_urls: set[str]) -> dict | None:
    for rss_url in RSS_SOURCES:
        entries = fetch_feed(rss_url)
        for entry in entries:
            url   = entry.get("link", "")
            title = entry.get("title", "")

            if url in posted_urls:
                continue
            if not is_teaching(entry):
                continue

            # Get excerpt
            rss_summary = clean_html(entry.get("summary", ""))
            excerpt = fetch_article_excerpt(url) or rss_summary[:600]

            if not excerpt or len(excerpt) < 50:
                continue

            logger.info(f"RSS match: {title[:60]}")
            return {
                "title":   title,
                "url":     url,
                "summary": excerpt,
                "type":    "audience" if "audience" in title.lower() else "angelus",
            }
    return None


# =========================================================
# FORMAT POST
# =========================================================
def extract_card_passage(full_summary: str, max_chars: int = 600) -> str:
    """
    From the full Vatican summary, pick the most meaningful passage for the card.
    Skips the opener ("In today's catechesis...") and finds the substantive content.
    """
    intro_skips = [
        "in today's catechesis,",
        "in today's general audience,",
        "i would like to share",
    ]
    text = full_summary.strip()
    lower = text.lower()

    for skip in intro_skips:
        idx = lower.find(skip)
        if idx == 0:  # Only skip if it's the VERY start
            dot = text.find(".", idx)
            if 0 < dot < 200:
                text = text[dot + 1:].strip()
            break

    if len(text) <= max_chars:
        return text

    # Find sentence boundary near max_chars
    for punct in (".", "!", "?"):
        idx = text.rfind(punct, 0, max_chars)
        if idx > max_chars * 0.5:
            return text[:idx + 1].strip()

    return text[:max_chars].rsplit(" ", 1)[0] + "…"


def format_papal_post(article: dict) -> tuple[str, Path | None]:
    """
    Format papal post text and generate card.
    User has Premium X — no character limit on post text.
    Card uses the most meaningful passage from the summary.
    """
    full_summary = re.sub(r"\s+", " ", article["summary"]).strip()
    url          = article["url"]
    today        = date.today()
    weekday      = today.weekday()

    # Label
    if weekday == 2:
        label = "Wednesday Audience — Pope Leo XIV"
    elif weekday == 6:
        label = "Angelus — Pope Leo XIV"
    else:
        label = "Pope Leo XIV"

    # Full post text — no truncation (Premium X)
    post_text = f"{label}\n\n{full_summary}\n\n{url}\n\n@Pontifex"

    # Card passage — most meaningful 2-3 sentences, skipping generic opener
    card_passage = extract_card_passage(full_summary, max_chars=500)

    # Generate card
    card_path = None
    try:
        date_str = today.strftime("%d %B %Y").lstrip("0")
        card_path = make_card(
            quote=card_passage,
            author="Pope Leo XIV",
            category="leo_xiv",
            source_type="history",
            date_label=date_str,
        )
    except Exception as e:
        logger.warning(f"Card generation failed: {e}")

    return post_text, card_path


# =========================================================
# MAIN
# =========================================================
def main():
    parser = argparse.ArgumentParser(description="adDominum papal feed")
    parser.add_argument("--live",  action="store_true", help="Post to X")
    parser.add_argument("--force", action="store_true",
                        help="Skip duplicate check")
    args = parser.parse_args()

    dry_run = not args.live
    logger.info(f"=== PAPAL FEED — {'DRY RUN' if dry_run else 'LIVE MODE'} ===")

    posted_urls = set() if args.force else load_papal_log()
    logger.info(f"Previously posted: {len(posted_urls)} articles")

    # Try Vatican.va directly first
    logger.info("Trying Vatican.va direct fetch...")
    article = try_vatican_direct(posted_urls)

    # Fall back to RSS
    if not article:
        logger.info("Trying RSS feeds...")
        try:
            article = try_rss_sources(posted_urls)
        except Exception as e:
            logger.error(f"RSS fallback failed: {e}")
            article = None

    if not article:
        logger.warning("No papal teaching found.")
        logger.info("Possible reasons:")
        logger.info("  - No audience/Angelus published yet this week")
        logger.info("  - All recent articles already posted")
        logger.info("  - Network issue reaching Vatican sources")
        return

    # Skip if already posted (belt and braces — the fetchers filter too)
    if article["url"] in posted_urls and not args.force:
        logger.info(f"Already posted: {article['title']}")
        return

    logger.info(f"Found: {article['title']}")
    logger.info(f"URL: {article['url']}")

    post_text, card_path = format_papal_post(article)

    # Preview
    logger.info("--- POST PREVIEW ---")
    for line in post_text.splitlines():
        logger.info(f"  {line}")
    logger.info(f"  ({len(post_text)} chars)")
    if card_path:
        logger.info(f"  Card: {card_path.name}")
    logger.info("--------------------")

    if dry_run:
        logger.info("DRY RUN complete. Use --live to post.")
        return

    # Post
    poster = Poster()
    success = poster.post(post_text, card_path)

    if success:
        save_papal_log(article["url"], article["title"])
        logger.info("Posted and logged.")
        if card_path and card_path.exists():
            card_path.unlink()
    else:
        logger.error("Posting failed.")


if __name__ == "__main__":
    main()
