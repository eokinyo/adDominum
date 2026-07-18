# builders/build_quotes_dataset.py
"""
Builds the unified quotes dataset from two sources:
  1. data/raw/catholic-quotes.md  — the complete markdown quote collection
  2. data/raw/*.json              — structured JSON files (used to cross-check
                                    and fill in any author fields missing from MD)

Output: data/processed/quotes_dataset.csv

Columns:
    id          — md5 hash of normalised quote text (stable, dedup key)
    quote       — cleaned quote text (no surrounding punctuation)
    author      — attributed author
    category    — topic category (Our Lady, Eucharist, etc.)
    season_tags — comma-separated scheduling tags (see CATEGORY_SEASON_MAP)
    status      — always "ready"
    confidence  — fixed per category
    risk        — always 1
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

# =========================================================
# PATHS
# =========================================================
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR   = BASE_DIR / "data" / "raw"
OUT_DIR   = BASE_DIR / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MD_FILE     = RAW_DIR / "catholic-quotes.md"
OUTPUT_CSV  = OUT_DIR / "quotes_dataset.csv"

JSON_FILES = {
    "Lent":                   RAW_DIR / "lent.json",
    "Prayer":                 RAW_DIR / "prayer.json",
    "Eucharist":              RAW_DIR / "eucharist.json",
    "Our Lady":               RAW_DIR / "our_lady.json",
    "Humility":               RAW_DIR / "humility.json",
    "Sacrament of Confession":RAW_DIR / "sacrament_confession.json",
    "Holy Purity":            RAW_DIR / "holy_purity.json",
    "Holy Angels":            RAW_DIR / "angels.json",
    "Faith":                  RAW_DIR / "faith.json",
    "Holy Rosary":            RAW_DIR / "holy_rosary.json",
    "Family Rosary":          RAW_DIR / "family_rosary.json",
    "Quotes on Vocation":     RAW_DIR / "vocation.json",
}

# =========================================================
# SEASON / SCHEDULING TAGS PER CATEGORY
# =========================================================
CATEGORY_SEASON_MAP = {
    "Lent":                    "lent",
    "Eucharist":               "thursday,corpus_christi,first_friday",
    "Our Lady":                "may,october,saturday,marian_feast",
    "Holy Rosary":             "may,october,saturday,rosary_feast",
    "Family Rosary":           "may,october,saturday",
    "Holy Angels":             "friday,sep29,oct02",
    "Sacrament of Confession": "thursday,first_friday,lent",
    "Humility":                "general",
    "Prayer":                  "general",
    "Faith":                   "general",
    "Holy Purity":             "general",
    "Quotes on Vocation":      "sunday,general",
}

CATEGORY_CONFIDENCE = {
    "Lent":                    9,
    "Eucharist":               9,
    "Our Lady":                9,
    "Holy Rosary":             9,
    "Family Rosary":           8,
    "Holy Angels":             8,
    "Sacrament of Confession": 9,
    "Humility":                8,
    "Prayer":                  9,
    "Faith":                   9,
    "Holy Purity":             8,
    "Quotes on Vocation":      8,
}


# =========================================================
# TEXT HELPERS
# =========================================================
# Normalise all quote/smart punctuation to plain ASCII
QUOTE_CHARS = '\u201c\u201d\u2018\u2019\u00ab\u00bb\u2039\u203a\u300c\u300d\xab\xbb\u201a\u201e'

def clean_quote(text: str) -> str:
    """Strip surrounding quote marks and normalise whitespace."""
    text = str(text or "").strip()
    text = text.strip(QUOTE_CHARS + '"\'')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def make_id(text: str) -> str:
    return hashlib.md5(' '.join(text.lower().split()).encode()).hexdigest()


# =========================================================
# AUTHOR EXTRACTION
# =========================================================
# Attribution patterns found in the MD file (order matters — most specific first)
_AUTHOR_PATTERNS = [
    # "Quote text" (Author Name)
    r'^["\u201c\u201d]?(.+?)["\u201c\u201d]?\s*\(([^)]{4,})\)\s*$',
    # Quote text - Author Name  OR  Quote text – Author Name
    r'^(.+?)\s+[-\u2013\u2014]\s+((?:St\.?|Bl\.?|Blessed|Pope|Father|Fr\.?|Bishop|'
    r'Venerable|Our Lady|Sister|Servant of God|Cardinal|Archbishop|'
    r'Saint|Doctor|Deacon|Abbot|Abbess|Msgr\.?)[^\n]{2,})$',
    # Quote text - Author Name (no title prefix required but must be capitalised)
    r'^(.+?)\s+[-\u2013\u2014]\s+([A-Z][a-zA-Z .\']+(?:,\s*[A-Z][a-zA-Z .\']+)*)$',
]

# Rescue patterns for malformed attributions where separator is missing or broken
# e.g. "...virtuous life. St John Chrysostom)"
_RESCUE_PATTERNS = [
    r'^(.+?)[.\s]+((?:St\.?\s|Bl\.?\s|Blessed\s|Pope\s|Father\s|Venerable\s|'
    r'Saint\s|Our Lady\s)[A-Z][a-zA-Z .\']{2,})\)?\s*$',
    r'^(.+?)[.\s]+((?:St|Bl)\.[A-Z][a-zA-Z .\']{2,})\)?\s*$',
]

def extract_author(raw: str) -> tuple[str, str]:
    """Return (quote_text, author). Falls back to (cleaned_text, 'Unknown')."""
    raw = raw.strip()

    # Primary patterns
    for pat in _AUTHOR_PATTERNS:
        m = re.match(pat, raw, re.DOTALL)
        if m:
            quote = clean_quote(m.group(1))
            author = m.group(2).strip().strip(QUOTE_CHARS + '"\'.,')
            if len(quote) > 10 and len(author) > 2:
                return quote, author

    # Rescue pass for malformed attributions
    for pat in _RESCUE_PATTERNS:
        m = re.match(pat, raw, re.DOTALL)
        if m:
            quote = clean_quote(m.group(1))
            author = m.group(2).strip().strip(QUOTE_CHARS + '"\'.,)')
            if len(quote) > 10 and len(author) > 2:
                return quote, author

    return clean_quote(raw), "Unknown"


# =========================================================
# PARSE MARKDOWN
# =========================================================
def parse_markdown() -> list[dict]:
    """Parse catholic-quotes.md into a list of dicts."""
    text = MD_FILE.read_text(encoding="utf-8")
    rows = []
    current_category = None

    for line in text.splitlines():
        stripped = line.strip()

        # Top-level heading = category
        if re.match(r'^# [^#]', stripped):
            current_category = stripped[2:].strip()
            continue

        # Skip sub-headings (## or ###) and blank lines
        if not stripped or stripped.startswith('#'):
            continue

        if current_category is None:
            continue

        quote, author = extract_author(stripped)

        # Skip lines that are clearly not quotes (too short, structural text)
        if len(quote) < 15:
            continue

        rows.append({
            "quote":    quote,
            "author":   author,
            "category": current_category,
        })

    return rows


# =========================================================
# LOAD JSON FILES (for cross-referencing better author data)
# =========================================================
def load_json_quotes() -> dict[str, list[dict]]:
    """Load all JSON files. Returns {category: [{quote, author}, ...]}"""
    result = {}
    for category, path in JSON_FILES.items():
        if not path.exists():
            print(f"  [WARN] Missing JSON: {path.name}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = []
        for item in data:
            raw = item.get("quote", "")
            quote, author = extract_author(raw)
            if len(quote) > 10:
                entries.append({"quote": quote, "author": author})
        result[category] = entries
    return result


# =========================================================
# MERGE
# =========================================================
def merge(md_rows: list[dict], json_map: dict[str, list[dict]]) -> list[dict]:
    """
    Merge MD and JSON rows. JSON rows provide better author attribution
    for the same quote text. MD is authoritative for content volume.
    """
    # Build a lookup of normalised-quote-key → best author from JSON
    json_author_lookup: dict[str, str] = {}
    for category, entries in json_map.items():
        for e in entries:
            key = make_id(e["quote"])
            if e["author"] and e["author"] != "Unknown":
                json_author_lookup[key] = e["author"]

    # Start from MD rows as the base
    seen_ids: set[str] = set()
    merged: list[dict] = []

    for row in md_rows:
        qid = make_id(row["quote"])
        if qid in seen_ids:
            continue
        seen_ids.add(qid)

        # Prefer JSON author if MD extracted "Unknown"
        author = row["author"]
        if author == "Unknown" and qid in json_author_lookup:
            author = json_author_lookup[qid]

        # Drop quotes with no attribution — unverifiable
        if author == "Unknown":
            continue

        category = row["category"]
        season_tags = CATEGORY_SEASON_MAP.get(category, "general")
        confidence  = CATEGORY_CONFIDENCE.get(category, 8)

        merged.append({
            "id":          qid,
            "quote":       row["quote"],
            "author":      author,
            "category":    category,
            "season_tags": season_tags,
            "topic":       "church",
            "dataset":     "quotes",
            "confidence":  confidence,
            "risk":        1,
            "status":      "ready",
        })

    # Add any JSON-only rows not already in MD
    for category, entries in json_map.items():
        for e in entries:
            qid = make_id(e["quote"])
            if qid in seen_ids:
                continue
            seen_ids.add(qid)

            season_tags = CATEGORY_SEASON_MAP.get(category, "general")
            confidence  = CATEGORY_CONFIDENCE.get(category, 8)

            merged.append({
                "id":          qid,
                "quote":       e["quote"],
                "author":      e["author"],
                "category":    category,
                "season_tags": season_tags,
                "topic":       "church",
                "dataset":     "quotes",
                "confidence":  confidence,
                "risk":        1,
                "status":      "ready",
            })

    return merged


# =========================================================
# WRITE CSV
# =========================================================
def write_csv(rows: list[dict]) -> None:
    fieldnames = ["id","quote","author","category","season_tags",
                  "topic","dataset","confidence","risk","status"]
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# =========================================================
# MAIN
# =========================================================
def main() -> None:
    print("[INFO] Building unified quotes dataset...")

    md_rows  = parse_markdown()
    json_map = load_json_quotes()
    rows     = merge(md_rows, json_map)

    # Report
    from collections import Counter
    cats = Counter(r["category"] for r in rows)
    unknown = sum(1 for r in rows if r["author"] == "Unknown")

    print(f"\n  Total quotes: {len(rows)}")
    print(f"  Unknown author: {unknown} ({unknown/len(rows)*100:.1f}%)")
    print("\n  By category:")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"    {cat:<30s} {count:3d}")

    write_csv(rows)
    print(f"\n  ✅ Saved → {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
