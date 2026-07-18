# core/queue_manager.py
"""
Queue Manager — builds and serves the daily post queue.

Reads from three datasets:
  - data/processed/quotes_dataset.csv       (saints & Catholic writers)
  - data/processed/benedict_dataset.csv     (Pope Benedict XVI)
  - data/processed/church_history_dataset.csv (curated historical events)

Uses the calendar router to determine which categories are eligible
today, then scores, filters, and selects the next post.

Quote-to-history ratio: 3:1 (one history post per three quote posts).
This is tracked via a lightweight counter in data/cache/post_counter.json.

Post log: logs/post_log.csv — used to avoid repeating recent posts.
Cache:    data/cache/current_queue.csv — expires after N hours.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from core.calendar_router import get_categories, get_all_eligible_categories
from utils.logger import setup_logging

logger = setup_logging("queue_manager")

# =========================================================
# PATHS
# =========================================================
BASE_DIR      = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
CACHE_DIR     = BASE_DIR / "data" / "cache"
LOG_DIR       = BASE_DIR / "logs"

QUOTES_CSV  = PROCESSED_DIR / "quotes_dataset.csv"
BENEDICT_CSV = PROCESSED_DIR / "benedict_dataset.csv"
HISTORY_CSV = PROCESSED_DIR / "church_history_dataset.csv"

POST_LOG        = LOG_DIR / "post_log.csv"
QUEUE_CACHE     = CACHE_DIR / "current_queue.csv"
COUNTER_FILE    = CACHE_DIR / "post_counter.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# CONFIG
# =========================================================
QUOTE_TO_HISTORY_RATIO = 3   # 1 history post per N quote posts
CACHE_HOURS            = 6   # Rebuild queue after this many hours
RECENT_POST_WINDOW     = 200 # Don't repeat any of the last N posts
MAX_QUEUE_SIZE         = 300


# =========================================================
# POST LOG
# =========================================================
def load_post_log() -> pd.DataFrame:
    if not POST_LOG.exists():
        return pd.DataFrame(columns=["timestamp", "id", "topic", "category", "post_text"])
    df = pd.read_csv(POST_LOG)
    for col in ["timestamp", "id", "topic", "category", "post_text"]:
        if col not in df.columns:
            df[col] = ""
    return df


def append_post_log(item: dict, post_text: str, status: str = "posted") -> None:
    POST_LOG.parent.mkdir(parents=True, exist_ok=True)
    write_header = not POST_LOG.exists()
    with POST_LOG.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "id", "topic", "category",
                             "author", "post_text", "status"])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            item.get("id", ""),
            item.get("topic", ""),
            item.get("category", ""),
            item.get("author", ""),
            post_text,
            status,
        ])


# =========================================================
# POST COUNTER (tracks quote vs history ratio)
# =========================================================
def load_counter() -> dict:
    if not COUNTER_FILE.exists():
        return {"quotes_since_history": 0}
    try:
        return json.loads(COUNTER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"quotes_since_history": 0}


def save_counter(counter: dict) -> None:
    COUNTER_FILE.write_text(json.dumps(counter), encoding="utf-8")


def increment_quote_counter() -> None:
    c = load_counter()
    c["quotes_since_history"] = c.get("quotes_since_history", 0) + 1
    save_counter(c)


def reset_history_counter() -> None:
    save_counter({"quotes_since_history": 0})


def should_post_history() -> bool:
    """Return True if we're due a history post based on ratio."""
    c = load_counter()
    return c.get("quotes_since_history", 0) >= QUOTE_TO_HISTORY_RATIO


# =========================================================
# LOAD DATASETS
# =========================================================
def load_quotes() -> pd.DataFrame:
    if not QUOTES_CSV.exists():
        logger.error(f"Quotes dataset not found: {QUOTES_CSV}")
        return pd.DataFrame()
    return pd.read_csv(QUOTES_CSV)


def load_benedict() -> pd.DataFrame:
    if not BENEDICT_CSV.exists():
        logger.error(f"Benedict dataset not found: {BENEDICT_CSV}")
        return pd.DataFrame()
    df = pd.read_csv(BENEDICT_CSV)
    # Normalise column name so it merges cleanly with quotes
    df["quote"] = df["quote"].astype(str)
    return df


def load_history() -> pd.DataFrame:
    if not HISTORY_CSV.exists():
        logger.error(f"Church history dataset not found: {HISTORY_CSV}")
        return pd.DataFrame()
    return pd.read_csv(HISTORY_CSV)


# =========================================================
# CACHE
# =========================================================
def cache_is_fresh() -> bool:
    if not QUEUE_CACHE.exists():
        return False
    age_hours = (datetime.now().timestamp() - QUEUE_CACHE.stat().st_mtime) / 3600
    return age_hours < CACHE_HOURS


def load_cache() -> pd.DataFrame:
    return pd.read_csv(QUEUE_CACHE)


def save_cache(df: pd.DataFrame) -> None:
    df.to_csv(QUEUE_CACHE, index=False)


# =========================================================
# RECENT POST IDs (to avoid repeats)
# =========================================================
def get_recent_ids(post_log: pd.DataFrame) -> set[str]:
    if post_log.empty or "id" not in post_log.columns:
        return set()
    return set(post_log.tail(RECENT_POST_WINDOW)["id"].astype(str).tolist())


# =========================================================
# SCORING
# =========================================================
def score_item(row: dict, today: date, decision: dict) -> float:
    """
    Score an item based on:
      - Base quality fields (confidence, risk)
      - Whether it matches today's primary vs secondary categories
      - Whether it matches today's season_tags
      - Small random jitter to prevent identical runs
    """
    confidence = float(row.get("confidence", 7))
    risk       = float(row.get("risk", 1))
    category   = str(row.get("category", ""))
    season_tags = str(row.get("season_tags", "general"))

    # Base score
    base = confidence - (risk * 0.5)

    # Category priority boost
    if category in decision.get("primary", []):
        base *= 1.3
    elif category in decision.get("secondary", []):
        base *= 1.0
    else:
        base *= 0.6

    # Season tag boost — reward items specifically tagged for today
    today_tags = _today_season_tags(today)
    item_tags  = {t.strip() for t in season_tags.split(",")}
    if item_tags & today_tags:   # intersection — at least one tag matches
        base *= 1.2

    # Small random jitter (±5%) for variety
    base *= random.uniform(0.95, 1.05)

    return round(max(1.0, base), 4)


def _today_season_tags(today: date) -> set[str]:
    """Return the set of season tags that apply today."""
    tags: set[str] = {"general"}
    month   = today.month
    weekday = today.weekday()  # 0=Mon, 5=Sat, 6=Sun
    day     = today.day

    if month == 5:
        tags |= {"may", "marian_feast"}
    if month == 10:
        tags |= {"october", "rosary_feast"}
    if weekday == 5:
        tags.add("saturday")
    if weekday == 6:
        tags.add("sunday")
    if weekday == 3:
        tags.add("thursday")
        if day <= 7:
            tags.add("corpus_christi")
    if weekday == 4:
        tags.add("friday")
        if day <= 7:
            tags.add("first_friday")

    # Lent / Easter detection via router
    from core.calendar_router import liturgical_season
    season = liturgical_season(today)
    if season == "lent":
        tags.add("lent")
    if season in ("easter", "holy_week"):
        tags.add("easter")

    return tags


# =========================================================
# BUILD QUOTE QUEUE
# =========================================================
def build_quote_queue(
    today: date,
    decision: dict,
    recent_ids: set[str],
) -> pd.DataFrame:
    """Build the pool of eligible quote posts for today."""

    quotes   = load_quotes()
    benedict = load_benedict()

    frames = []

    # --- Saints / Catholic writers quotes ---
    if not quotes.empty:
        eligible_cats = set(decision["primary"] + decision["secondary"])
        # Always include general pool categories
        eligible_cats |= {"Prayer", "Faith", "Humility", "Holy Purity", "Vocation"}

        q = quotes[quotes["category"].isin(eligible_cats)].copy()
        q["source_type"] = "quote"
        frames.append(q)

    # --- Benedict XVI ---
    # Always eligible; boosted on his feast days via scoring
    if not benedict.empty:
        b = benedict.copy()
        b["source_type"] = "benedict"
        frames.append(b)

    if not frames:
        logger.warning("No quote data loaded")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Remove recently posted
    if recent_ids:
        df = df[~df["id"].astype(str).isin(recent_ids)]

    if df.empty:
        logger.warning("All quotes recently posted — resetting recent window")
        # If we've genuinely exhausted the pool, return everything
        df = pd.concat(frames, ignore_index=True)

    # Score
    df["score"] = df.apply(
        lambda row: score_item(row.to_dict(), today, decision), axis=1
    )

    df = df.sort_values("score", ascending=False).head(MAX_QUEUE_SIZE)
    logger.info(f"Quote queue built: {len(df)} items")
    return df.reset_index(drop=True)


# =========================================================
# BUILD HISTORY QUEUE
# =========================================================
def build_history_queue(
    today: date,
    recent_ids: set[str],
) -> pd.DataFrame:
    """
    Build the pool of eligible church history posts for today.
    Prioritises events whose month_day matches today or is nearby.
    """
    history = load_history()
    if history.empty:
        return pd.DataFrame()

    history = history.copy()

    # Remove recently posted
    if recent_ids:
        history = history[~history["id"].astype(str).isin(recent_ids)]

    if history.empty:
        history = load_history()

    # Score: prioritise events on or near today's date
    today_mmdd = f"{today.month:02d}-{today.day:02d}"

    def history_score(row: dict) -> float:
        mmdd = str(row.get("month_day", ""))
        base = float(row.get("confidence", 9))

        # Exact date match
        if mmdd == today_mmdd:
            base *= 2.0
        else:
            # Within 7 days either side
            try:
                event_date = date(today.year, int(mmdd[:2]), int(mmdd[3:]))
                diff = abs((event_date - today).days)
                if diff <= 3:
                    base *= 1.5
                elif diff <= 7:
                    base *= 1.2
            except ValueError:
                pass

        base *= random.uniform(0.95, 1.05)
        return round(base, 4)

    history["score"] = history.apply(lambda r: history_score(r.to_dict()), axis=1)
    history["source_type"] = "history"

    history = history.sort_values("score", ascending=False).head(50)
    logger.info(f"History queue built: {len(history)} items")
    return history.reset_index(drop=True)


# =========================================================
# SELECTION
# =========================================================
def choose_quote(queue: pd.DataFrame) -> Optional[dict]:
    """Weighted random selection from the top quote candidates."""
    if queue.empty:
        return None

    candidates = queue.head(40).copy()
    candidates["score"] = pd.to_numeric(
        candidates["score"], errors="coerce"
    ).fillna(1.0).clip(lower=0.1)

    try:
        chosen = candidates.sample(n=1, weights="score").iloc[0].to_dict()
        logger.info(
            f"Quote selected → [{chosen.get('category')}] "
            f"{chosen.get('author','?')} | score={chosen.get('score',0):.2f}"
        )
        return chosen
    except Exception as e:
        logger.error(f"Quote selection failed: {e}")
        return candidates.iloc[0].to_dict()


def choose_history(queue: pd.DataFrame) -> Optional[dict]:
    """Weighted random selection from top history candidates."""
    if queue.empty:
        return None

    candidates = queue.head(10).copy()
    candidates["score"] = pd.to_numeric(
        candidates["score"], errors="coerce"
    ).fillna(1.0).clip(lower=0.1)

    try:
        chosen = candidates.sample(n=1, weights="score").iloc[0].to_dict()
        logger.info(
            f"History selected → [{chosen.get('category')}] "
            f"{chosen.get('title','?')[:60]} | score={chosen.get('score',0):.2f}"
        )
        return chosen
    except Exception as e:
        logger.error(f"History selection failed: {e}")
        return candidates.iloc[0].to_dict()


# =========================================================
# MAIN ENTRY POINT
# =========================================================
def get_next_post(today: date | None = None) -> Optional[dict]:
    """
    Return the next item to post.

    Decides between quote and history based on the 3:1 ratio,
    then selects from the appropriate pool using today's calendar routing.
    """
    if today is None:
        today = date.today()

    decision    = get_categories(today)
    post_log    = load_post_log()
    recent_ids  = get_recent_ids(post_log)

    logger.info(f"Routing decision: {decision['reason']}")

    # Decide: quote or history?
    history_due = should_post_history() and decision["history"]

    if history_due:
        history_queue = build_history_queue(today, recent_ids)
        item = choose_history(history_queue)
        if item:
            reset_history_counter()
            return item
        else:
            logger.warning("History queue empty — falling back to quote")

    # Quote post
    quote_queue = build_quote_queue(today, decision, recent_ids)
    item = choose_quote(quote_queue)
    if item:
        increment_quote_counter()
        return item

    logger.error("Both queues empty — nothing to post")
    return None


# =========================================================
# CLI
# =========================================================
if __name__ == "__main__":
    import sys

    today = date.today()
    if len(sys.argv) > 1:
        try:
            today = date.fromisoformat(sys.argv[1])
        except ValueError:
            print(f"Invalid date: {sys.argv[1]}")
            sys.exit(1)

    print(f"\nBuilding queue for {today.strftime('%A, %d %B %Y')}...\n")

    item = get_next_post(today)

    if item:
        print(f"  Type:      {item.get('source_type', '?')}")
        print(f"  Topic:     {item.get('topic', '?')}")
        print(f"  Category:  {item.get('category', '?')}")
        print(f"  Author:    {item.get('author', item.get('title', '?'))}")
        print(f"  Score:     {item.get('score', 0):.3f}")
        print(f"\n  Content:")
        content = item.get("quote") or item.get("summary") or ""
        print(f"  {content[:280]}")
    else:
        print("  No post available.")
