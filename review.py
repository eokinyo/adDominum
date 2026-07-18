# review.py
"""
adDominum — Review Mode

Generates a preview of the next N posts without posting anything.
Each post shows:
  - The post text (exactly what would appear on X)
  - The image card (saved to outputs/review/)
  - The routing reason (why this category was chosen today)

Usage:
    python review.py           # preview next 10 posts
    python review.py --count 5 # preview next 5 posts
    python review.py --date 2026-12-08  # preview for a specific date

Cards are saved to outputs/review/ for you to inspect.
Nothing is posted to X.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path
import shutil

from utils.logger import setup_logging
from core.calendar_router import get_categories, liturgical_season
from core.queue_manager import (
    get_next_post, append_post_log, load_post_log,
    build_quote_queue, build_history_queue, choose_quote, choose_history,
    should_post_history, increment_quote_counter, reset_history_counter,
    load_counter, save_counter,
)
from processors.formatter import format_post

logger = setup_logging("review")

REVIEW_DIR = Path(__file__).resolve().parent / "outputs" / "review"


def clear_review_dir():
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    # Delete files individually to avoid Windows/OneDrive folder lock
    for f in REVIEW_DIR.iterdir():
        try:
            if f.is_file():
                f.unlink()
        except PermissionError:
            pass  # Skip locked files silently


def preview_posts(count: int, start_date: date) -> None:
    clear_review_dir()

    print()
    print("=" * 60)
    print("  adDominum — Review Mode")
    print(f"  Starting date: {start_date.strftime('%A, %d %B %Y')}")
    print(f"  Previewing {count} posts")
    print("=" * 60)

    # Save real counter state and restore after
    real_counter = load_counter()

    # Track simulated post IDs to avoid repeats during preview
    simulated_ids: set[str] = set()
    results = []

    today = start_date
    post_num = 0

    while post_num < count:
        decision = get_categories(today)
        season   = liturgical_season(today)

        # Determine quote vs history
        history_due = should_post_history() and decision["history"]

        if history_due:
            queue = build_history_queue(today, simulated_ids)
            item  = choose_history(queue)
            if item:
                reset_history_counter()
            else:
                queue = build_quote_queue(today, decision, simulated_ids)
                item  = choose_quote(queue)
                if item:
                    increment_quote_counter()
        else:
            queue = build_quote_queue(today, decision, simulated_ids)
            item  = choose_quote(queue)
            if item:
                increment_quote_counter()

        if not item:
            print(f"\n  ⚠️  Post {post_num+1}: No item available for {today}")
            today += timedelta(days=1)
            continue

        # Track to avoid repeats in this preview
        item_id = str(item.get("id", ""))
        if item_id:
            simulated_ids.add(item_id)

        # Format + generate card
        result    = format_post(item)
        post_text = result.get("text", "")
        card_path = result.get("card_path")

        # Copy card to review dir with numbered name
        review_card = None
        if card_path and card_path.exists():
            review_name = f"{post_num+1:02d}_{card_path.name}"
            review_card = REVIEW_DIR / review_name
            shutil.copy2(card_path, review_card)

        results.append({
            "num":       post_num + 1,
            "date":      today,
            "season":    season,
            "reason":    decision["reason"],
            "category":  item.get("category", ""),
            "author":    item.get("author", item.get("title", "")),
            "post_text": post_text,
            "card":      review_card,
        })

        # Print preview
        print(f"\n{'─'*60}")
        print(f"  Post {post_num+1:02d} │ {today.strftime('%a %d %b')} │ "
              f"{season.upper()} │ {decision['reason']}")
        print(f"  Category: {item.get('category','')} │ "
              f"{item.get('author', item.get('title',''))[:45]}")
        print(f"\n  Tweet text:")
        for line in post_text.splitlines():
            print(f"    {line}")
        print(f"\n  Card: {review_card.name if review_card else 'not generated'}")

        post_num += 1
        # Advance date every 2 posts (rough simulation of 55-110 min intervals)
        if post_num % 2 == 0:
            today += timedelta(days=1)

    # Restore real counter
    save_counter(real_counter)

    # Write summary CSV
    summary_path = REVIEW_DIR / "review_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["#", "date", "season", "reason",
                         "category", "author", "post_text", "card"])
        for r in results:
            writer.writerow([
                r["num"], r["date"].isoformat(), r["season"],
                r["reason"], r["category"], r["author"],
                r["post_text"], r["card"].name if r["card"] else "",
            ])

    print(f"\n{'='*60}")
    print(f"  Review complete.")
    print(f"  Cards saved to:   outputs/review/")
    print(f"  Summary saved to: outputs/review/review_summary.csv")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="adDominum review mode")
    parser.add_argument("--count", type=int, default=10,
                        help="Number of posts to preview (default: 10)")
    parser.add_argument("--date", type=str, default=None,
                        help="Start date in YYYY-MM-DD format (default: today)")
    args = parser.parse_args()

    start = date.today()
    if args.date:
        try:
            start = date.fromisoformat(args.date)
        except ValueError:
            print(f"Invalid date: {args.date}. Use YYYY-MM-DD.")
            return

    preview_posts(args.count, start)


if __name__ == "__main__":
    main()