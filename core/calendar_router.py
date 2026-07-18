# core/calendar_router.py
"""
Calendar Router — the scheduling brain of adDominum.

Given today's date, returns which content categories should be
drawn from, in priority order.

Logic layers (applied in order, highest priority first):
  1. Fixed feast days (specific MM-DD dates)
  2. Moveable feasts (calculated from Easter)
  3. Liturgical seasons (Advent, Lent, Easter, Ordinary Time)
  4. Day-of-week rules (Thursdays, Saturdays, Sundays, Fridays)
  5. Month rules (May = Marian month, October = Rosary month)
  6. General fallback pool

Each call to get_categories() returns:
  {
    "primary":   [list of category names to draw from first],
    "secondary": [list of category names as fallback],
    "history":   True/False  (whether to include a church history post),
    "reason":    "Human-readable explanation of why"
  }
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import TypedDict


# =========================================================
# TYPES
# =========================================================
class RoutingDecision(TypedDict):
    primary:   list[str]
    secondary: list[str]
    history:   bool
    reason:    str


# =========================================================
# EASTER CALCULATION (Anonymous Gregorian algorithm)
# =========================================================
def easter(year: int) -> date:
    """Return the date of Easter Sunday for the given year."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day   = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


# =========================================================
# MOVEABLE FEASTS
# =========================================================
def moveable_feasts(year: int) -> dict[date, str]:
    """Return a dict of {date: feast_name} for moveable feasts."""
    e = easter(year)
    feasts: dict[date, str] = {}

    # Lent
    feasts[e - timedelta(days=46)] = "Ash Wednesday"
    feasts[e - timedelta(days=7)]  = "Palm Sunday"
    feasts[e - timedelta(days=3)]  = "Holy Thursday"
    feasts[e - timedelta(days=2)]  = "Good Friday"
    feasts[e - timedelta(days=1)]  = "Holy Saturday"

    # Easter season
    feasts[e]                      = "Easter Sunday"
    feasts[e + timedelta(days=1)]  = "Easter Monday"
    feasts[e + timedelta(days=39)] = "Ascension Thursday"
    feasts[e + timedelta(days=49)] = "Pentecost Sunday"
    feasts[e + timedelta(days=56)] = "Trinity Sunday"
    feasts[e + timedelta(days=60)] = "Corpus Christi"

    # Other moveable
    # First Friday of each month is already handled in day-of-week logic
    return feasts


# =========================================================
# LITURGICAL SEASON
# =========================================================
def liturgical_season(today: date) -> str:
    """
    Return the current liturgical season.
    Seasons: advent, christmas, lent, holy_week, easter, ordinary
    """
    year = today.year
    e    = easter(year)

    # Advent: starts 4 Sundays before Christmas (Dec 25)
    christmas    = date(year, 12, 25)
    advent_start = christmas - timedelta(days=christmas.weekday() + 1 + 21)
    # (go back to the Sunday 3 weeks before the Sunday before Christmas)
    # Simpler: Advent is 4 Sundays before Christmas
    # Find the Sunday on or before Dec 3 (earliest possible Advent Sunday)
    dec_3 = date(year, 12, 3)
    advent_start = dec_3 - timedelta(days=dec_3.weekday() % 7)
    # Recalculate properly: 4th Sunday before Dec 25
    days_to_sunday = (christmas.weekday() + 1) % 7
    fourth_sunday_before = christmas - timedelta(days=days_to_sunday + 21)
    advent_start = fourth_sunday_before

    ash_wednesday = e - timedelta(days=46)
    holy_thursday = e - timedelta(days=3)
    easter_end    = e + timedelta(days=49)  # Pentecost
    christmas_day = date(year, 12, 25)
    epiphany      = date(year + 1, 1, 6)   # Epiphany ends Christmas season

    # Christmas season: Dec 25 → Jan 6 (spans year boundary)
    if today >= christmas_day:
        return "christmas"
    if today >= advent_start:
        return "advent"
    if today >= easter_end:
        return "ordinary"
    if today >= e:
        return "easter"
    if today >= holy_thursday:
        return "holy_week"
    if today >= ash_wednesday:
        return "lent"
    if today >= date(year, 1, 7):
        return "ordinary"
    # Jan 1–6: Christmas season (carry-over from previous year)
    return "christmas"


# =========================================================
# FIXED FEAST DAYS (MM-DD)
# =========================================================
FIXED_FEASTS: dict[str, dict] = {
    # ---- January ----
    "01-01": {"name": "Solemnity of Mary, Mother of God",
              "primary": ["Our Lady"], "secondary": ["Holy Rosary", "Prayer"]},
    "01-17": {"name": "St Anthony of Egypt",
              "primary": ["Humility", "Prayer"], "secondary": ["Faith"]},
    "01-28": {"name": "St Thomas Aquinas",
              "primary": ["Faith", "Doctrine"], "secondary": ["Prayer"]},

    # ---- February ----
    "02-02": {"name": "Presentation of the Lord (Candlemas)",
              "primary": ["Our Lady", "Eucharist"], "secondary": ["Prayer"]},
    "02-11": {"name": "Our Lady of Lourdes",
              "primary": ["Our Lady", "Holy Rosary"], "secondary": ["Sacrament of Confession"]},
    "02-16": {"name": "Birthday of Pope Benedict XVI",
              "primary": ["Benedict"], "secondary": ["Faith"]},
    "02-22": {"name": "Chair of St Peter",
              "primary": ["Faith", "Doctrine"], "secondary": ["Prayer", "Humility"]},

    # ---- March ----
    "03-07": {"name": "Sts Perpetua and Felicitas",
              "primary": ["Faith", "Humility"], "secondary": ["Prayer"]},
    "03-17": {"name": "St Patrick",
              "primary": ["Faith", "Vocation"], "secondary": ["Prayer"]},
    "03-19": {"name": "St Joseph, Spouse of the Blessed Virgin Mary",
              "primary": ["Our Lady", "Vocation"], "secondary": ["Humility"]},
    "03-25": {"name": "Annunciation of the Lord",
              "primary": ["Our Lady", "Faith"], "secondary": ["Holy Rosary", "Prayer"]},

    # ---- April ----
    "04-02": {"name": "Death of Pope John Paul II (2005)",
              "primary": ["Benedict", "Faith"], "secondary": ["Prayer", "Humility"]},
    "04-19": {"name": "Election of Pope Benedict XVI (2005)",
              "primary": ["Benedict"], "secondary": ["Faith", "Doctrine"]},
    "04-23": {"name": "St George, Martyr",
              "primary": ["Faith", "Humility"], "secondary": ["Prayer"]},

    # ---- May ----
    "05-01": {"name": "St Joseph the Worker",
              "primary": ["Vocation", "Humility"], "secondary": ["Prayer"]},
    "05-13": {"name": "Our Lady of Fatima",
              "primary": ["Our Lady", "Holy Rosary"], "secondary": ["Family Rosary", "Prayer"]},
    "05-26": {"name": "St Philip Neri",
              "primary": ["Prayer", "Humility"], "secondary": ["Sacrament of Confession"]},
    "05-31": {"name": "Visitation of the Blessed Virgin Mary",
              "primary": ["Our Lady"], "secondary": ["Holy Rosary", "Humility"]},

    # ---- June ----
    "06-13": {"name": "St Anthony of Padua",
              "primary": ["Prayer", "Faith"], "secondary": ["Humility"]},
    "06-21": {"name": "St Aloysius Gonzaga",
              "primary": ["Holy Purity", "Vocation"], "secondary": ["Prayer"]},
    "06-24": {"name": "Nativity of St John the Baptist",
              "primary": ["Faith", "Prayer"], "secondary": ["Humility", "Vocation"]},
    "06-29": {"name": "Sts Peter and Paul, Apostles",
              "primary": ["Faith", "Doctrine"], "secondary": ["Prayer", "Vocation"]},

    # ---- July ----
    "07-06": {"name": "St Thomas More, Martyr",
              "primary": ["Faith", "Humility"], "secondary": ["Vocation"]},
    "07-11": {"name": "St Benedict of Nursia",
              "primary": ["Prayer", "Humility"], "secondary": ["Vocation", "Faith"]},
    "07-16": {"name": "Our Lady of Mount Carmel",
              "primary": ["Our Lady", "Holy Rosary"], "secondary": ["Prayer", "Holy Purity"]},
    "07-22": {"name": "St Mary Magdalene",
              "primary": ["Faith", "Humility"], "secondary": ["Prayer", "Sacrament of Confession"]},
    "07-25": {"name": "St James the Apostle",
              "primary": ["Faith", "Vocation"], "secondary": ["Prayer"]},

    # ---- August ----
    "08-04": {"name": "St John Vianney, Patron of Priests",
              "primary": ["Sacrament of Confession", "Prayer"], "secondary": ["Vocation", "Eucharist"]},
    "08-09": {"name": "St Teresa Benedicta of the Cross (Edith Stein)",
              "primary": ["Faith", "Prayer"], "secondary": ["Humility"]},
    "08-14": {"name": "St Maximilian Kolbe",
              "primary": ["Our Lady", "Holy Rosary"], "secondary": ["Faith", "Humility"]},
    "08-15": {"name": "Assumption of the Blessed Virgin Mary",
              "primary": ["Our Lady"], "secondary": ["Holy Rosary", "Faith", "Prayer"]},
    "08-28": {"name": "St Augustine of Hippo",
              "primary": ["Faith", "Prayer"], "secondary": ["Sacrament of Confession", "Humility"]},

    # ---- September ----
    "09-08": {"name": "Nativity of the Blessed Virgin Mary",
              "primary": ["Our Lady", "Holy Rosary"], "secondary": ["Family Rosary", "Prayer"]},
    "09-14": {"name": "Exaltation of the Holy Cross",
              "primary": ["Faith", "Humility"], "secondary": ["Prayer"]},
    "09-15": {"name": "Our Lady of Sorrows",
              "primary": ["Our Lady"], "secondary": ["Prayer", "Humility", "Lent"]},
    "09-27": {"name": "St Vincent de Paul",
              "primary": ["Humility", "Vocation"], "secondary": ["Prayer"]},
    "09-29": {"name": "Michaelmas — Sts Michael, Gabriel & Raphael",
              "primary": ["Holy Angels"], "secondary": ["Prayer", "Faith"]},
    "09-30": {"name": "St Jerome, Doctor of the Church",
              "primary": ["Faith", "Prayer"], "secondary": ["Humility"]},

    # ---- October ----
    "10-01": {"name": "St Thérèse of Lisieux, Doctor of the Church",
              "primary": ["Prayer", "Humility"], "secondary": ["Holy Purity", "Faith"]},
    "10-02": {"name": "Feast of the Guardian Angels",
              "primary": ["Holy Angels"], "secondary": ["Prayer", "Faith"]},
    "10-04": {"name": "St Francis of Assisi",
              "primary": ["Humility", "Prayer"], "secondary": ["Holy Purity", "Vocation"]},
    "10-07": {"name": "Our Lady of the Rosary",
              "primary": ["Holy Rosary", "Our Lady"], "secondary": ["Family Rosary", "Prayer"]},
    "10-15": {"name": "St Teresa of Avila, Doctor of the Church",
              "primary": ["Prayer"], "secondary": ["Faith", "Humility"]},
    "10-16": {"name": "Election of Pope John Paul II (1978)",
              "primary": ["Faith", "Doctrine"], "secondary": ["Prayer"]},
    "10-28": {"name": "Sts Simon and Jude, Apostles",
              "primary": ["Faith", "Vocation"], "secondary": ["Prayer"]},

    # ---- November ----
    "11-01": {"name": "All Saints Day",
              "primary": ["Faith", "Prayer"], "secondary": ["Humility", "Vocation"]},
    "11-02": {"name": "All Souls Day",
              "primary": ["Prayer", "Faith"], "secondary": ["Sacrament of Confession"]},
    "11-09": {"name": "Dedication of the Lateran Basilica",
              "primary": ["Faith", "Eucharist"], "secondary": ["Prayer"]},
    "11-21": {"name": "Presentation of the Blessed Virgin Mary",
              "primary": ["Our Lady"], "secondary": ["Holy Purity", "Prayer"]},

    # ---- December ----
    "12-03": {"name": "St Francis Xavier",
              "primary": ["Faith", "Vocation"], "secondary": ["Prayer"]},
    "12-08": {"name": "Immaculate Conception of the Blessed Virgin Mary",
              "primary": ["Our Lady", "Holy Purity"], "secondary": ["Holy Rosary", "Faith"]},
    "12-09": {"name": "Our Lady of Guadalupe (apparition date)",
              "primary": ["Our Lady", "Holy Rosary"], "secondary": ["Faith", "Prayer"]},
    "12-12": {"name": "Our Lady of Guadalupe (feast day)",
              "primary": ["Our Lady", "Holy Rosary"], "secondary": ["Family Rosary", "Faith"]},
    "12-25": {"name": "Nativity of Our Lord Jesus Christ",
              "primary": ["Faith", "Prayer"], "secondary": ["Our Lady", "Eucharist"]},
    "12-26": {"name": "St Stephen, First Martyr",
              "primary": ["Faith", "Humility"], "secondary": ["Prayer"]},
    "12-27": {"name": "St John the Apostle and Evangelist",
              "primary": ["Faith", "Vocation"], "secondary": ["Prayer", "Eucharist"]},
    "12-31": {"name": "Death of Pope Benedict XVI (2022)",
              "primary": ["Benedict"], "secondary": ["Faith", "Prayer"]},
}


# =========================================================
# GENERAL POOL — used as fallback on ordinary days
# =========================================================
GENERAL_POOL = ["Prayer", "Faith", "Humility", "Holy Purity", "Vocation"]

MARIAN_POOL  = ["Our Lady", "Holy Rosary", "Family Rosary"]

EUCHARIST_POOL = ["Eucharist", "Sacrament of Confession"]

ANGELS_POOL = ["Holy Angels"]


# =========================================================
# MAIN ROUTER
# =========================================================
def get_categories(today: date | None = None) -> RoutingDecision:
    """
    Return a RoutingDecision for the given date (defaults to today).
    """
    if today is None:
        today = date.today()

    year    = today.year
    month   = today.month
    day     = today.day
    weekday = today.weekday()   # 0=Mon … 6=Sun
    mmdd    = f"{month:02d}-{day:02d}"

    # --------------------------------------------------
    # 1. Check moveable feasts first
    # --------------------------------------------------
    feasts = moveable_feasts(year)
    if today in feasts:
        feast_name = feasts[today]
        if feast_name in ("Holy Thursday", "Corpus Christi"):
            return RoutingDecision(
                primary=["Eucharist", "Sacrament of Confession"],
                secondary=GENERAL_POOL,
                history=True,
                reason=f"Moveable feast: {feast_name}",
            )
        if feast_name == "Good Friday":
            return RoutingDecision(
                primary=["Lent", "Faith", "Humility"],
                secondary=["Holy Rosary", "Prayer"],
                history=False,
                reason=f"Moveable feast: {feast_name}",
            )
        if feast_name in ("Ash Wednesday", "Palm Sunday", "Holy Saturday"):
            return RoutingDecision(
                primary=["Lent", "Sacrament of Confession", "Humility"],
                secondary=["Prayer", "Faith"],
                history=False,
                reason=f"Moveable feast: {feast_name}",
            )
        if feast_name in ("Easter Sunday", "Easter Monday"):
            return RoutingDecision(
                primary=["Faith", "Eucharist"],
                secondary=["Our Lady", "Prayer"],
                history=False,
                reason=f"Moveable feast: {feast_name}",
            )
        if feast_name == "Pentecost Sunday":
            return RoutingDecision(
                primary=["Faith", "Prayer", "Vocation"],
                secondary=GENERAL_POOL,
                history=True,
                reason=f"Moveable feast: {feast_name}",
            )
        if feast_name == "Trinity Sunday":
            return RoutingDecision(
                primary=["Faith", "Doctrine"],
                secondary=GENERAL_POOL,
                history=True,
                reason=f"Moveable feast: {feast_name}",
            )
        if feast_name == "Ascension Thursday":
            return RoutingDecision(
                primary=["Faith", "Eucharist", "Vocation"],
                secondary=GENERAL_POOL,
                history=True,
                reason=f"Moveable feast: {feast_name}",
            )

    # --------------------------------------------------
    # 2. Fixed feast days
    # --------------------------------------------------
    if mmdd in FIXED_FEASTS:
        feast = FIXED_FEASTS[mmdd]
        return RoutingDecision(
            primary=feast["primary"],
            secondary=feast["secondary"],
            history=True,
            reason=f"Fixed feast: {feast['name']}",
        )

    # --------------------------------------------------
    # 3. Liturgical season
    # --------------------------------------------------
    season = liturgical_season(today)

    if season == "lent":
        return RoutingDecision(
            primary=["Lent", "Sacrament of Confession", "Humility"],
            secondary=["Prayer", "Faith", "Holy Purity"],
            history=True,
            reason="Liturgical season: Lent",
        )
    if season == "advent":
        return RoutingDecision(
            primary=["Our Lady", "Faith", "Prayer"],
            secondary=["Holy Rosary", "Humility", "Vocation"],
            history=True,
            reason="Liturgical season: Advent",
        )
    if season == "easter":
        return RoutingDecision(
            primary=["Faith", "Eucharist", "Prayer"],
            secondary=["Our Lady", "Vocation"],
            history=True,
            reason="Liturgical season: Easter",
        )
    if season == "christmas":
        return RoutingDecision(
            primary=["Faith", "Our Lady", "Prayer"],
            secondary=["Holy Rosary", "Humility"],
            history=False,
            reason="Liturgical season: Christmas",
        )

    # --------------------------------------------------
    # 4. Month rules (May and October)
    # --------------------------------------------------
    if month == 5:
        if weekday == 5:   # Saturday
            return RoutingDecision(
                primary=MARIAN_POOL,
                secondary=["Prayer", "Faith"],
                history=False,
                reason="May — Marian month (Saturday)",
            )
        return RoutingDecision(
            primary=["Our Lady", "Holy Rosary"],
            secondary=GENERAL_POOL + ["Family Rosary"],
            history=True,
            reason="May — Marian month",
        )

    if month == 10:
        if weekday == 5:   # Saturday
            return RoutingDecision(
                primary=MARIAN_POOL,
                secondary=["Prayer", "Faith"],
                history=False,
                reason="October — Rosary month (Saturday)",
            )
        return RoutingDecision(
            primary=["Holy Rosary", "Our Lady"],
            secondary=GENERAL_POOL + ["Holy Angels"],
            history=True,
            reason="October — Rosary month",
        )

    # --------------------------------------------------
    # 5. Day-of-week rules (ordinary time)
    # --------------------------------------------------

    # Saturday — always Marian
    if weekday == 5:
        return RoutingDecision(
            primary=MARIAN_POOL,
            secondary=GENERAL_POOL,
            history=False,
            reason="Saturday — Marian day",
        )

    # Sunday — vocation and faith
    if weekday == 6:
        return RoutingDecision(
            primary=["Vocation", "Faith", "Prayer"],
            secondary=GENERAL_POOL,
            history=True,
            reason="Sunday — vocation and faith",
        )

    # Thursday — Eucharist (Last Supper / Holy Hour tradition)
    if weekday == 3:
        # Check if First Thursday of the month
        is_first_thursday = day <= 7
        return RoutingDecision(
            primary=EUCHARIST_POOL,
            secondary=GENERAL_POOL,
            history=True,
            reason="Thursday — Eucharistic day" + (" (First Thursday)" if is_first_thursday else ""),
        )

    # Friday — Cross, angels, penance
    if weekday == 4:
        # First Friday
        is_first_friday = day <= 7
        if is_first_friday:
            return RoutingDecision(
                primary=["Eucharist", "Sacrament of Confession", "Holy Purity"],
                secondary=GENERAL_POOL,
                history=True,
                reason="First Friday — Sacred Heart / Confession",
            )
        return RoutingDecision(
            primary=["Holy Angels", "Humility", "Holy Purity"],
            secondary=GENERAL_POOL,
            history=True,
            reason="Friday — penance and angels",
        )

    # --------------------------------------------------
    # 6. General fallback (Mon, Tue, Wed in ordinary time)
    # --------------------------------------------------
    return RoutingDecision(
        primary=GENERAL_POOL,
        secondary=MARIAN_POOL + EUCHARIST_POOL,
        history=True,
        reason="Ordinary time — general pool",
    )


# =========================================================
# CONVENIENCE HELPERS
# =========================================================
def get_all_eligible_categories(today: date | None = None) -> list[str]:
    """Return a flat, deduplicated list of all eligible categories for today."""
    decision = get_categories(today)
    seen: set[str] = set()
    result: list[str] = []
    for cat in decision["primary"] + decision["secondary"]:
        if cat not in seen:
            seen.add(cat)
            result.append(cat)
    return result


def should_post_history(today: date | None = None) -> bool:
    """Return True if today's schedule includes a church history post."""
    return get_categories(today)["history"]


# =========================================================
# CLI — run directly to preview today's routing
# =========================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # Accept a date argument: python calendar_router.py 2026-12-08
        try:
            check_date = date.fromisoformat(sys.argv[1])
        except ValueError:
            print(f"Invalid date: {sys.argv[1]}. Use YYYY-MM-DD format.")
            sys.exit(1)
    else:
        check_date = date.today()

    decision = get_categories(check_date)
    season   = liturgical_season(check_date)

    print(f"\n{'='*55}")
    print(f"  adDominum — Calendar Router")
    print(f"{'='*55}")
    print(f"  Date:          {check_date.strftime('%A, %d %B %Y')}")
    print(f"  Liturgical:    {season.upper()}")
    print(f"  Reason:        {decision['reason']}")
    print(f"\n  Primary:       {', '.join(decision['primary'])}")
    print(f"  Secondary:     {', '.join(decision['secondary'])}")
    print(f"  History post:  {'Yes' if decision['history'] else 'No'}")

    print(f"\n  All eligible:  {', '.join(get_all_eligible_categories(check_date))}")
    print(f"{'='*55}\n")

    # Show a few nearby dates
    print("  Upcoming schedule:")
    for i in range(7):
        d = check_date + timedelta(days=i)
        dec = get_categories(d)
        s   = liturgical_season(d)
        print(f"    {d.strftime('%a %d %b')}  [{s[:3].upper()}]  "
              f"{dec['reason'][:45]:<45}  "
              f"→ {', '.join(dec['primary'][:2])}")
    print()
