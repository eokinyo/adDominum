# utils/card_maker.py
"""
Card Maker — generates image cards for adDominum posts.

Design:
  - Full-bleed background photo (lightly blurred)
  - Frosted glass panel (semi-transparent, rounded corners)
  - Circular portrait top-left (overlapping panel edge)
  - Author name bold, centred
  - Quote text italic serif, centred, larger and better vertically centred
  - "Follow @e_okinyo" bottom-right

Card: 1200x675 (16:9)
Fonts: Caladea preferred (Windows-safe), Lora as fallback
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# =========================================================
# PATHS
# =========================================================
BASE_DIR     = Path(__file__).resolve().parent.parent
ASSETS_DIR   = BASE_DIR / "assets"
BG_DIR       = ASSETS_DIR / "backgrounds"
PORTRAIT_DIR = ASSETS_DIR / "portraits"
OUTPUT_DIR   = BASE_DIR / "outputs" / "cards"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================
# CARD DIMENSIONS
# =========================================================
CARD_W = 1200
CARD_H = 675

# Panel — slightly wider, taller
PANEL_LEFT   = 140
PANEL_TOP    = 55
PANEL_RIGHT  = CARD_W - 140
PANEL_BOTTOM = CARD_H - 55
PANEL_RADIUS = 28

# Portrait circle
PORTRAIT_D      = 115   # diameter
PORTRAIT_BORDER = 5
PORTRAIT_CX     = PANEL_LEFT + 78   # circle centre x
PORTRAIT_CY     = PANEL_TOP         # sits on top edge of panel

# Text zone inside panel
TEXT_PAD_X = 70
TEXT_LEFT  = PANEL_LEFT + TEXT_PAD_X
TEXT_RIGHT = PANEL_RIGHT - TEXT_PAD_X

HANDLE     = "@e_okinyo"
HANDLE_PAD = 20

# =========================================================
# FONTS
# Priority: Caladea (Windows-safe) → Lora → DejaVu fallback
# =========================================================
_WIN_FONT_DIRS = [
    "C:/Windows/Fonts",
    "C:/Users/{}/AppData/Local/Microsoft/Windows/Fonts",
]
_LINUX_FONT_BASE = "/usr/share/fonts/truetype"

FONT_PATHS = {
    "regular": [
        # Windows
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/georgia.ttf",
        # Linux
        f"{_LINUX_FONT_BASE}/crosextra/Caladea-Regular.ttf",
        f"{_LINUX_FONT_BASE}/google-fonts/Lora-Variable.ttf",
        f"{_LINUX_FONT_BASE}/dejavu/DejaVuSans.ttf",
    ],
    "italic": [
        "C:/Windows/Fonts/georgiai.ttf",
        "C:/Windows/Fonts/calibrii.ttf",
        f"{_LINUX_FONT_BASE}/crosextra/Caladea-Italic.ttf",
        f"{_LINUX_FONT_BASE}/google-fonts/Lora-Italic-Variable.ttf",
        f"{_LINUX_FONT_BASE}/dejavu/DejaVuSans-Oblique.ttf",
    ],
    "bold": [
        "C:/Windows/Fonts/georgiab.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        f"{_LINUX_FONT_BASE}/crosextra/Caladea-Bold.ttf",
        f"{_LINUX_FONT_BASE}/dejavu/DejaVuSans-Bold.ttf",
    ],
}


def load_font(style: str = "regular", size: int = 32) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS.get(style, FONT_PATHS["regular"]):
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# =========================================================
# BACKGROUND SELECTION
# =========================================================
CATEGORY_BACKGROUND: dict[str, str] = {
    # Marian
    "our lady": "our_lady", "holy rosary": "our_lady",
    "family rosary": "our_lady", "apparition": "our_lady",
    # Papal / Eucharistic / History
    "eucharist": "st_peters", "benedict": "st_peters",
    "church_history": "st_peters", "papacy": "st_peters",
    "council": "st_peters", "dogma": "st_peters",
    "saint": "st_peters", "liturgy": "st_peters",
    # Penitential
    "lent": "lent", "sacrament of confession": "lent",
    "humility": "lent", "martyrdom": "lent",
    # Spiritual / light
    "holy angels": "angels", "faith": "angels",
    "prayer": "angels", "quotes on vocation": "angels",
    "vocation": "angels", "holy purity": "angels",
    "evangelisation": "angels",
    # Doctrine categories (Benedict)
    "theology": "st_peters", "doctrine": "st_peters",
    "life": "st_peters", "marriage": "st_peters",
    "confession": "lent", "society": "st_peters",
}

BACKGROUND_FILES: dict[str, list[str]] = {
    "our_lady":  ["our_lady.png", "our_lady.jpg"],
    "st_peters": ["st_peters.jpg", "st_peters.png"],
    "lent":      ["lent.jpg", "lent.png"],
    "angels":    ["angels.jpg", "general.jpg", "general.png"],
    "general":   ["general.jpg", "general.png", "st_peters.jpg"],
}


def get_background(category: str) -> Image.Image:
    key       = CATEGORY_BACKGROUND.get(category.lower(), "general")
    filenames = BACKGROUND_FILES.get(key, []) + ["st_peters.jpg"]
    for fname in filenames:
        path = BG_DIR / fname
        if path.exists():
            try:
                return scale_to_fill(Image.open(path).convert("RGB"), CARD_W, CARD_H)
            except Exception:
                continue
    return make_fallback_bg()


def scale_to_fill(img: Image.Image, w: int, h: int) -> Image.Image:
    sw, sh = img.size
    scale  = max(w / sw, h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    img    = img.resize((nw, nh), Image.LANCZOS)
    return img.crop(((nw - w) // 2, (nh - h) // 2,
                     (nw - w) // 2 + w, (nh - h) // 2 + h))


def make_fallback_bg() -> Image.Image:
    img  = Image.new("RGB", (CARD_W, CARD_H))
    draw = ImageDraw.Draw(img)
    for y in range(CARD_H):
        t = y / CARD_H
        draw.line([(0, y), (CARD_W, y)],
                  fill=(int(15+t*25), int(20+t*35), int(50+t*60)))
    return img


# =========================================================
# PORTRAIT LOOKUP
# =========================================================
PORTRAIT_FOLDERS: dict[str, list[str]] = {
    "our lady":                ["ourLady"],
    "holy rosary":             ["holyRosary", "ourLady"],
    "family rosary":           ["familyRosary", "holyRosary"],
    "eucharist":               ["Eucharist"],
    "sacrament of confession": ["confession"],
    "holy angels":             ["holyAngels"],
    "lent":                    ["lent"],
    "prayer":                  ["prayer"],
    "faith":                   ["faith"],
    "humility":                ["humility"],
    "holy purity":             ["holyPurity"],
    "quotes on vocation":      ["vocation"],
    "vocation":                ["vocation"],
    "leo_xiv":                 ["leoXIV", "faith"],
    "theology":                ["faith", "vocation"],
    "doctrine":                ["faith"],
    "life":                    ["faith"],
    "marriage":                ["faith"],
    "confession":              ["confession"],
    "society":                 ["faith"],
}

ALL_FOLDERS = [
    "leoXIV", "faith", "prayer", "humility", "Eucharist", "holyRosary",
    "ourLady", "vocation", "lent", "holyAngels", "holyPurity",
    "confession", "familyRosary",
]


def _norm(name: str) -> str:
    name = re.sub(
        r'^(St\.?\s|Bl\.?\s|Blessed\s|Pope\s|Father\s|Fr\.?\s|Venerable\s|'
        r'Saint\s|Cardinal\s|Bishop\s|Archbishop\s|Sister\s|Msgr\.?\s)',
        '', name, flags=re.IGNORECASE).strip()
    name = unicodedata.normalize('NFD', name)
    return ''.join(c for c in name if unicodedata.category(c) != 'Mn')


def find_portrait(author: str, category: str) -> Optional[Image.Image]:
    if not author or author == "Unknown":
        return None
    raw      = author.strip()
    norm     = _norm(raw)
    variants = list(dict.fromkeys([
        raw, norm,
        raw.replace("St. ", "").replace("St ", "").strip(),
        norm.replace(" of ", " ").strip(),
    ]))
    exts     = [".jpg", ".jpeg", ".png", ".JPG", ".PNG", ".JPEG", ".webp"]
    priority = PORTRAIT_FOLDERS.get(category.lower(), [])
    search   = priority + [f for f in ALL_FOLDERS if f not in priority]

    for folder_name in search:
        folder = PORTRAIT_DIR / folder_name
        if not folder.exists():
            continue
        for v in variants:
            for ext in exts:
                p = folder / f"{v}{ext}"
                if p.exists():
                    try:
                        return Image.open(p).convert("RGBA")
                    except Exception:
                        pass
        try:
            for f in folder.iterdir():
                stem = f.stem.lower()
                for v in variants:
                    if stem == v.lower() or v.lower() in stem:
                        try:
                            return Image.open(f).convert("RGBA")
                        except Exception:
                            pass
        except Exception:
            pass
    return None


def crop_circle(img: Image.Image, size: int) -> Image.Image:
    img  = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img.convert("RGBA"), (0, 0), mask)
    return out


# =========================================================
# TEXT HELPERS
# =========================================================
def wrap_text(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        test = f"{cur} {word}".strip() if cur else word
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_text(draw, text: str, style: str, max_w: int, max_h: int,
             start: int = 46, minimum: int = 26):
    """Find the largest font size where all text fits."""
    size = start
    while size >= minimum:
        font  = load_font(style, size)
        lines = wrap_text(draw, text, font, max_w)
        lh    = int(size * 1.5)
        if len(lines) * lh <= max_h:
            return font, lines, lh
        size -= 2
    font  = load_font(style, minimum)
    lines = wrap_text(draw, text, font, max_w)
    lh    = int(minimum * 1.5)
    max_l = max_h // lh
    lines = lines[:max_l]
    if lines:
        lines[-1] = lines[-1].rstrip(".") + "…"
    return font, lines, lh


# =========================================================
# MAIN CARD MAKER
# =========================================================
def make_card(
    quote: str,
    author: str,
    category: str,
    source_type: str = "quote",
    date_label: str = "",
    output_path: Optional[Path] = None,
) -> Path:

    # --- Background ---
    bg   = get_background(category).filter(ImageFilter.GaussianBlur(radius=3))
    card = bg.convert("RGBA")

    # --- Panel ---
    pw, ph = PANEL_RIGHT - PANEL_LEFT, PANEL_BOTTOM - PANEL_TOP
    panel  = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle(
        [0, 0, pw - 1, ph - 1], radius=PANEL_RADIUS,
        fill=(235, 235, 235, 175)
    )
    card.paste(panel, (PANEL_LEFT, PANEL_TOP), panel)
    draw = ImageDraw.Draw(card)

    # --- Portrait ---
    portrait_img = find_portrait(author, category)
    has_portrait = portrait_img is not None
    if has_portrait:
        circle  = crop_circle(portrait_img, PORTRAIT_D)
        bd      = PORTRAIT_D + PORTRAIT_BORDER * 2
        border  = Image.new("RGBA", (bd, bd), (0, 0, 0, 0))
        ImageDraw.Draw(border).ellipse((0, 0, bd-1, bd-1), fill=(255,255,255,245))
        border.paste(circle, (PORTRAIT_BORDER, PORTRAIT_BORDER), circle)
        card.paste(border, (PORTRAIT_CX - bd//2, PORTRAIT_CY - bd//2), border)

    # --- Text area bounds ---
    text_w   = TEXT_RIGHT - TEXT_LEFT

    # Top: leave room below portrait overlap
    if has_portrait:
        text_top = PANEL_TOP + PORTRAIT_D // 2 + 22
    else:
        text_top = PANEL_TOP + 32

    # Bottom: leave room for handle
    text_bot = PANEL_BOTTOM - 48
    text_h   = text_bot - text_top

    # --- Author / date line ---
    author_font = load_font("bold", 30)
    if source_type == "history" and date_label:
        label = date_label
    elif source_type == "benedict":
        label = "Pope Benedict XVI"
    else:
        label = author if author and author != "Unknown" else ""

    label_h = 0
    if label:
        ab     = draw.textbbox((0, 0), label, font=author_font)
        label_h = ab[3] - ab[1]
        lx     = TEXT_LEFT + (text_w - (ab[2]-ab[0])) // 2
        draw.text((lx, text_top), label, font=author_font, fill=(40, 40, 40))

    # --- Quote text ---
    quote_top = text_top + label_h + (18 if label else 0)
    quote_h   = text_bot - quote_top

    style = "regular" if source_type == "history" else "italic"
    qfont, qlines, lh = fit_text(
        draw, quote, style, text_w, quote_h,
        start=46, minimum=26
    )

    # Vertically centre the quote block
    total_text_h = len(qlines) * lh
    y = quote_top + max(0, (quote_h - total_text_h) // 2)

    for line in qlines:
        lb = draw.textbbox((0, 0), line, font=qfont)
        lw = lb[2] - lb[0]
        draw.text((TEXT_LEFT + (text_w - lw) // 2, y),
                  line, font=qfont, fill=(25, 25, 25))
        y += lh

    # --- Handle ---
    hfont = load_font("regular", 22)
    hb    = draw.textbbox((0, 0), HANDLE, font=hfont)
    draw.text(
        (PANEL_RIGHT - (hb[2]-hb[0]) - HANDLE_PAD,
         PANEL_BOTTOM - (hb[3]-hb[1]) - HANDLE_PAD),
        HANDLE, font=hfont, fill=(75, 75, 75)
    )

    # --- Save ---
    if output_path is None:
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        cat = re.sub(r"[^a-zA-Z0-9_]", "_", category.lower())
        output_path = OUTPUT_DIR / f"card_{cat}_{ts}.jpg"

    card.convert("RGB").save(str(output_path), "JPEG", quality=92)
    return output_path


# =========================================================
# CONVENIENCE WRAPPER
# =========================================================
def make_card_for_item(item: dict) -> Optional[Path]:
    try:
        source_type = str(item.get("source_type", "quote")).lower()
        dataset     = str(item.get("dataset", "")).lower()
        category    = str(item.get("category", "general"))

        if dataset == "benedict" or item.get("topic") == "benedict":
            source_type = "benedict"
            quote, author, date_label = item.get("quote",""), "Pope Benedict XVI", ""
        elif dataset == "church_history" or source_type == "history":
            source_type = "history"
            quote  = item.get("summary", "")
            author = item.get("title", "")
            try:
                m  = int(item.get("month", 0))
                d  = int(item.get("day", 0))
                y  = int(item.get("year", 0))
                mn = ["","January","February","March","April","May","June",
                      "July","August","September","October","November","December"]
                date_label = f"{d} {mn[m]} {y} AD" if y else f"{d} {mn[m]}"
            except Exception:
                date_label = ""
        else:
            quote      = item.get("quote", "")
            author     = item.get("author", "")
            date_label = ""

        return make_card(quote, author, category, source_type, date_label) if quote else None
    except Exception as e:
        print(f"Card generation failed: {e}")
        return None


# =========================================================
# CLI TEST
# =========================================================
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    tests = [
        {"source_type": "quote", "dataset": "quotes", "topic": "church",
         "category": "Our Lady",
         "quote": "In dangers, in doubts, in difficulties, think of Mary, call upon Mary. "
                  "Let not her name depart from your lips, never suffer it to leave your heart.",
         "author": "St. Bernard of Clairvaux"},
        {"source_type": "benedict", "dataset": "benedict", "topic": "benedict",
         "category": "Doctrine",
         "quote": "A dictatorship of relativism is spreading, where nothing is absolute "
                  "and everything is negotiable. We must not submit to it.",
         "author": "Pope Benedict XVI"},
        {"source_type": "history", "dataset": "church_history", "topic": "church",
         "category": "apparition",
         "summary": "Our Lady appears for the first time to three shepherd children — "
                    "Lucia, Francisco, and Jacinta — at the Cova da Iria in Fatima, Portugal. "
                    "She would appear on the 13th of each month until October.",
         "title": "Marian Apparition", "month": 5, "day": 13, "year": 1917},
        {"source_type": "quote", "dataset": "quotes", "topic": "church",
         "category": "Prayer",
         "quote": "Never will anyone who says his Rosary every day be led astray. "
                  "This is a statement that I would gladly sign with my blood.",
         "author": "St. Louis de Montfort"},
        {"source_type": "quote", "dataset": "quotes", "topic": "church",
         "category": "Lent",
         "quote": "Lent is like a long retreat during which we can turn back into ourselves "
                  "and listen to the voice of God, in order to defeat the temptations of "
                  "the Evil One.",
         "author": "Pope Benedict XVI"},
    ]

    print("\nadDominum — Card Maker Test")
    print("=" * 50)
    for item in tests:
        path = make_card_for_item(item)
        if path:
            print(f"  ✅ [{item['category']}] → {path.name}")
        else:
            print(f"  ❌ [{item['category']}] — failed")
    print()
