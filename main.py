# main.py
"""
adDominum — Main entry point.

Run:
    python main.py           # run today's plan, then exit
    python main.py --once    # single post and exit
    python main.py --live    # override dry_run from command line

Posting window: 08:00 — 20:00 local time.
Posts per day: randomly chosen between 4 and 10 each morning.

The script now runs ONE day's plan and exits cleanly after the final post.
Windows Task Scheduler restarts it at 07:58 the next morning. Nothing idles
overnight, and there is no path back into the loop once the plan is done.

If the script starts late (e.g. the PC was off at 08:00 and the task fired
on boot at 14:00), the plan is built across the REMAINING window rather than
from 08:00 — so it never dumps a backlog of posts all at once.
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
POSTS_MIN     = config.get("posts_per_day_min", 4)
POSTS_MAX     = config.get("posts_per_day_max", 10)
JITTER_MINS   = 15    # ± minutes of randomness around the base interval
MIN_GAP_MINS  = 25    # never schedule two posts closer than this
GRACE_MINS    = 20    # a target older than this is skipped, not fired late
HEARTBEAT     = 15 * 60   # log a "still waiting" line this often


# =========================================================
# WINDOW HELPERS
# =========================================================
def window_open_at(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, WINDOW_START, 0, 0)


def window_close_at(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, WINDOW_END, 0, 0)


def in_posting_window() -> bool:
    hour = datetime.now().hour
    return WINDOW_START <= hour < WINDOW_END


def sleep_until_window() -> bool:
    """
    Sleep until today's window opens.

    Returns True if we are (now) inside the window, False if the window has
    already closed for today — in which case the caller should exit and let
    the scheduler start us again tomorrow.
    """
    now = datetime.now()

    if in_posting_window():
        return True

    if now.hour >= WINDOW_END:
        return False

    opens = window_open_at(now.date())
    secs  = (opens - now).total_seconds()
    logger.info(
        f"Window opens at {opens.strftime('%H:%M')} — "
        f"sleeping {int(secs // 60)} minutes."
    )
    time.sleep(max(0, secs))
    return True


def wait_until(target: datetime) -> None:
    """Sleep until the target time, with a heartbeat line every 15 minutes."""
    while True:
        now = datetime.now()
        remaining = (target - now).total_seconds()

        if remaining <= 0:
            return

        if remaining > HEARTBEAT:
            logger.info(
                f"Next post at {target.strftime('%H:%M')} — "
                f"{int(remaining // 60)} min remaining."
            )
            time.sleep(HEARTBEAT)
        else:
            # Single final sleep. Never loops tightly: even at 1 second
            # remaining this sleeps a full second before re-checking.
            time.sleep(max(1.0, remaining))


# =========================================================
# DAILY POST PLAN
# =========================================================
def make_daily_plan() -> tuple[int, int, list[datetime]]:
    """
    Decide how many posts to make today and calculate target times.

    The plan spans from now (or window open, whichever is later) to window
    close, so a late start produces a sensible smaller plan instead of a
    backlog. Returns (posts_planned, interval_mins, [target_datetimes]).
    """
    now    = datetime.now()
    today  = now.date()
    opens  = window_open_at(today)
    closes = window_close_at(today)

    start     = max(opens, now + timedelta(minutes=2))
    remaining = int((closes - start).total_seconds() // 60)

    if remaining < MIN_GAP_MINS:
        logger.info(
            f"Only {remaining} minutes left in today's window — "
            f"not enough time for a meaningful plan."
        )
        return 0, 0, []

    n = random.randint(POSTS_MIN, POSTS_MAX)

    # Don't cram posts together if we started late.
    max_n = max(1, remaining // MIN_GAP_MINS)
    if n > max_n:
        logger.info(
            f"Late start — reducing today's plan from {n} to {max_n} posts "
            f"to keep at least {MIN_GAP_MINS} minutes between them."
        )
        n = max_n

    interval = remaining // n

    targets: list[datetime] = []
    t = start
    for i in range(n):
        jitter = 0 if i == 0 else random.randint(-JITTER_MINS, JITTER_MINS)
        post_t = t + timedelta(minutes=jitter)
        post_t = max(start, min(post_t, closes - timedelta(minutes=5)))
        targets.append(post_t)
        t += timedelta(minutes=interval)

    targets.sort()

    logger.info(
        f"Daily plan: {n} posts | ~{interval} min intervals | "
        f"First at {targets[0].strftime('%H:%M')} | "
        f"Last at {targets[-1].strftime('%H:%M')}"
    )
    return n, interval, targets


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
# RUN ONE DAY
# =========================================================
def run_day(poster: Poster) -> int:
    """
    Work through today's plan, then return the number of successful posts.
    This function always terminates — there is no unbounded loop in it.
    """
    _, _, targets = make_daily_plan()
    if not targets:
        return 0

    posted = 0
    total  = len(targets)

    for i, target in enumerate(targets, start=1):
        now = datetime.now()

        # Target already well in the past — skip rather than fire late.
        if now > target + timedelta(minutes=GRACE_MINS):
            logger.info(
                f"Skipping post {i} of {total} — scheduled "
                f"{target.strftime('%H:%M')} has already passed."
            )
            continue

        if now < target:
            logger.info(
                f"Post {i} of {total} scheduled at {target.strftime('%H:%M')} "
                f"({int((target - now).total_seconds() // 60)} min away)."
            )
            wait_until(target)

        try:
            if run_cycle(poster):
                posted += 1
        except Exception as e:
            logger.error(f"Post {i} of {total} failed with an error: {e}")
            logger.info("Continuing to the next scheduled post.")
            time.sleep(60)

    return posted


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

    try:
        if args.once or not config.loop_forever:
            run_cycle(poster)
            return

        if not sleep_until_window():
            logger.info(
                f"Today's posting window has already closed. Exiting — "
                f"the scheduler will start me again at "
                f"{WINDOW_START:02d}:00 tomorrow."
            )
            return

        posted = run_day(poster)

        logger.info("=" * 55)
        logger.info(
            f"  Daily plan complete — {posted} posts made. "
            f"Exiting until {WINDOW_START:02d}:00 tomorrow."
        )
        logger.info("=" * 55)

    except KeyboardInterrupt:
        logger.info("Shutting down gracefully")
        sys.exit(0)


if __name__ == "__main__":
    main()
