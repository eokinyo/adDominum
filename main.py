# main.py
"""
adDominum — Main entry point.

Run:
    python main.py           # continuous loop
    python main.py --once    # single post and exit
    python main.py --live    # override dry_run from command line

Posting window: 08:00 — 20:00 local time.
Posts per day: randomly chosen between 4 and 10 each morning.
The window (720 minutes) is divided by the chosen number, giving
the base interval, with ±15 minutes of jitter on each post.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from utils.logger import setup_logging
from utils.config import config
from core.queue_manager import get_next_post, append_post_log
from processors.formatter import format_post
from processors.dedupe import is_duplicate
from publishing.poster import Poster

logger = setup_logging("main")

WINDOW_START  = config.get("post_window_start", 8)
WINDOW_END    = config.get("post_window_end",  20)
WINDOW_MINS   = (WINDOW_END - WINDOW_START) * 60   # 720 minutes
POSTS_MIN     = config.get("posts_per_day_min", 4)
POSTS_MAX     = config.get("posts_per_day_max", 10)
JITTER_MINS   = 15    # ± minutes of randomness around the base interval
SLEEP_CHECK   = 15 * 60


# =========================================================
# DAILY POST PLAN
# =========================================================
def make_daily_plan() -> tuple[int, int, list[datetime]]:
    """
    Decide how many posts to make today and calculate target times.
    Returns (posts_planned, interval_mins, [target_datetimes])
    """
    n        = random.randint(POSTS_MIN, POSTS_MAX)
    interval = WINDOW_MINS // n          # base interval in minutes

    # Build target post times starting from window open
    today     = date.today()
    window_open = datetime(today.year, today.month, today.day,
                           WINDOW_START, 0, 0)

    targets = []
    t = window_open
    for i in range(n):
        # Add jitter: ±JITTER_MINS, but keep within window
        jitter = random.randint(-JITTER_MINS, JITTER_MINS)
        post_t = t + timedelta(minutes=jitter)

        # Clamp to window bounds
        window_close = datetime(today.year, today.month, today.day,
                                WINDOW_END, 0, 0)
        post_t = max(window_open, min(post_t, window_close - timedelta(minutes=5)))
        targets.append(post_t)
        t += timedelta(minutes=interval)

    logger.info(
        f"Daily plan: {n} posts | "
        f"~{interval} min intervals | "
        f"First at {targets[0].strftime('%H:%M')} | "
        f"Last at {targets[-1].strftime('%H:%M')}"
    )
    return n, interval, targets


# =========================================================
# WINDOW HELPERS
# =========================================================
def in_posting_window() -> bool:
    hour = datetime.now().hour
    return WINDOW_START <= hour < WINDOW_END


def wait_until(target: datetime) -> None:
    """Sleep until the target time, logging progress every 15 minutes."""
    while True:
        now = datetime.now()
        if now >= target:
            return
        remaining = (target - now).total_seconds()
        if remaining > SLEEP_CHECK:
            logger.info(
                f"Next post at {target.strftime('%H:%M')} — "
                f"waiting ({int(remaining // 60)} min remaining)..."
            )
            time.sleep(SLEEP_CHECK)
        else:
            time.sleep(max(1, remaining - 5))  # wake up a few secs early


def wait_for_window() -> None:
    """Sleep until the posting window opens."""
    while not in_posting_window():
        now       = datetime.now()
        tomorrow  = now + timedelta(days=1)
        wake_time = datetime(tomorrow.year, tomorrow.month, tomorrow.day,
                             WINDOW_START, 0, 0)
        if now.hour < WINDOW_START:
            wake_time = datetime(now.year, now.month, now.day,
                                 WINDOW_START, 0, 0)

        logger.info(
            f"Outside posting window ({WINDOW_START:02d}:00–{WINDOW_END:02d}:00). "
            f"Current time: {now.strftime('%H:%M')}. "
            f"Window opens at {wake_time.strftime('%H:%M')}. "
            f"Checking again in 15 minutes..."
        )
        time.sleep(SLEEP_CHECK)


# =========================================================
# CLEANUP
# =========================================================
def cleanup_card(card_path: Path | None) -> None:
    if card_path and card_path.exists():
        try:
            card_path.unlink()
            logger.debug(f"Deleted posted card: {card_path.name}")
        except Exception as e:
            logger.warning(f"Could not delete card {card_path.name}: {e}")


# =========================================================
# SINGLE CYCLE
# =========================================================
def run_cycle(poster: Poster) -> bool:
    logger.info(f"--- Cycle starting at {datetime.now().strftime('%H:%M:%S')} ---")

    item = get_next_post()
    if not item:
        logger.warning("No item available — skipping cycle")
        return False

    logger.info(
        f"Selected: [{item.get('category')}] "
        f"{item.get('author', item.get('title', '?'))[:50]}"
    )

    result    = format_post(item)
    post_text = result.get("text", "")
    card_path = result.get("card_path")

    if not post_text:
        logger.warning("Formatter returned empty text — skipping")
        return False

    if is_duplicate(post_text, [], content_key=item.get("id", "")):
        logger.info("Duplicate detected — skipping")
        return False

    success = poster.post(post_text, card_path)

    status = "posted" if success else "failed"
    if not config.dry_run:
        append_post_log(item, post_text, status)
        if success:
            cleanup_card(card_path)

    return success


# =========================================================
# MAIN
# =========================================================
def main():
    parser = argparse.ArgumentParser(description="adDominum X automation")
    parser.add_argument("--once", action="store_true",
                        help="Run a single cycle and exit")
    parser.add_argument("--live", action="store_true",
                        help="Override dry_run=True in settings")
    args = parser.parse_args()

    if args.live:
        config._data["dry_run"] = False
        logger.warning("LIVE MODE — posts will be published to X")

    logger.info("=" * 55)
    logger.info("  adDominum starting")
    logger.info(f"  {config}")
    logger.info(
        f"  Posting window: {WINDOW_START:02d}:00 — {WINDOW_END:02d}:00 "
        f"| {POSTS_MIN}–{POSTS_MAX} posts per day"
    )
    logger.info("=" * 55)

    poster = Poster()

    if args.once or not config.loop_forever:
        run_cycle(poster)
        return

    logger.info("Starting continuous loop...")
    current_day  = None
    targets      = []
    target_index = 0

    while True:
        try:
            # Wait until we're in the posting window
            wait_for_window()

            today = date.today()

            # New day — build a fresh plan
            if today != current_day:
                current_day  = today
                _, _, targets = make_daily_plan()
                target_index = 0
                logger.info(
                    f"New day plan: {len(targets)} posts scheduled "
                    f"between {targets[0].strftime('%H:%M')} "
                    f"and {targets[-1].strftime('%H:%M')}"
                )

            # All posts for today done — wait for tomorrow
            if target_index >= len(targets):
                logger.info(
                    f"All {len(targets)} posts completed for today. "
                    f"Waiting for tomorrow's window..."
                )
                wait_for_window()
                continue

            # Wait until the next scheduled post time
            next_target = targets[target_index]
            now         = datetime.now()

            if now < next_target:
                logger.info(
                    f"Next post scheduled at {next_target.strftime('%H:%M')} "
                    f"({int((next_target - now).total_seconds() // 60)} min away) "
                    f"— post {target_index + 1} of {len(targets)} today"
                )
                wait_until(next_target)

            # Post
            run_cycle(poster)
            target_index += 1

            # Show next post time if there is one
            if target_index < len(targets):
                nxt = targets[target_index]
                mins = int((nxt - datetime.now()).total_seconds() // 60)
                logger.info(
                    f"Next post attempt at {nxt.strftime('%H:%M')} "
                    f"({mins} minutes)"
                )

        except KeyboardInterrupt:
            logger.info("Shutting down gracefully")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            logger.info("Waiting 5 minutes before retry...")
            time.sleep(300)


if __name__ == "__main__":
    main()
