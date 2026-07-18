# Church Automation

X (Twitter) automation for Catholic devotional content.

## Scope

Two content lanes:

**1. Quotes** — Saints, Popes, and Catholic writers, organised by the liturgical
calendar. Quotes are drawn from the appropriate category based on the current
liturgical season, feast days, and day of week.

**2. Church History** — "On this day" historical events from reliable Catholic
sources (papal elections, councils, canonisations, martyrs). Posted at a 1:3
ratio with quotes (one history post per three quote posts).

**3. Live Papal Feed** — Vatican News RSS + @Pontifex monitoring. Runs as a
separate daily script, not part of the main quote loop.

## Content Categories

| Category             | When to post                                              |
|----------------------|-----------------------------------------------------------|
| Lent                 | Ash Wednesday → Holy Saturday                             |
| Eucharist            | Thursdays, Corpus Christi, First Fridays                  |
| Our Lady             | May, October, Saturdays, Marian feast days                |
| Holy Rosary          | May, October, Saturdays, feast of Our Lady of the Rosary  |
| Family Rosary        | May, October, Saturdays                                   |
| Holy Angels          | Sep 29 (Michaelmas), Oct 2 (Guardian Angels), Fridays     |
| Sacrament/Confession | Thursdays, First Fridays, Lent                            |
| Benedict XVI         | Feb 16 (feast), Apr 19 (election anniversary), general    |
| Prayer               | General pool — any day                                    |
| Faith                | General pool — any day                                    |
| Humility             | General pool — any day                                    |
| Holy Purity          | General pool — any day                                    |
| Vocation             | Sundays (weighted), general pool                          |

## Project Structure

```
church_automation/
├── main.py                    # Entry point
├── requirements.txt
├── config/
│   ├── api_keys.env           # X API credentials (never commit)
│   └── settings.yaml          # Runtime settings
├── builders/
│   ├── build_quotes_dataset.py   # Parse MD + JSON → unified CSV
│   ├── build_benedict_dataset.py # Benedict XVI teachings → CSV
│   └── build_church_dataset.py   # Church history from reliable sources
├── core/
│   ├── calendar_router.py     # Maps today's date → content categories
│   ├── queue_manager.py       # Builds and serves the post queue
│   └── scorer.py              # Scores items for selection
├── content/
│   └── templates/
│       ├── quote_templates.py
│       └── church_templates.py
├── processors/
│   ├── formatter.py           # Converts items to post text
│   └── dedupe.py
├── publishing/
│   ├── poster.py              # Posts to X via API
│   ├── scheduler.py
│   └── papal_feed.py          # Vatican News RSS daily script
├── utils/
│   ├── config.py
│   ├── logging.py
│   └── card_maker.py          # Image card generator
├── data/
│   ├── raw/                   # Source files (MD, JSON)
│   ├── processed/             # Built CSVs
│   └── cache/                 # Runtime queue cache
├── logs/
└── outputs/
    └── cards/                 # Generated image cards
```

## Setup

1. Copy `config/api_keys.env.example` to `config/api_keys.env` and fill in credentials
2. Run builders in order:
   ```
   python builders/build_quotes_dataset.py
   python builders/build_benedict_dataset.py
   python builders/build_church_dataset.py
   ```
3. Run `python main.py` — dry run by default (`dry_run: true` in settings.yaml)

## Notes

- Never commit `config/api_keys.env`
- Delete `data/cache/current_queue.csv` to force a queue rebuild
- The queue cache expires after 6 hours automatically
