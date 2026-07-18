# builders/build_church_dataset.py
"""
Builds the church history dataset from curated events.

Rather than scraping Wikimedia (unreliable, requires filtering),
this uses a hand-verified set of significant events in Church history:
  - Papal elections, deaths, and key acts
  - Ecumenical Councils
  - Dogmatic definitions
  - Canonisations and beatifications of major saints
  - Marian apparitions and related feasts
  - Major moments of evangelisation and martyrdom
  - Key Church reforms and milestones

Each event is tied to a calendar date (MM-DD) so the queue manager
can serve it on or near the anniversary.

Output: data/processed/church_history_dataset.csv
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parent.parent
OUT_DIR    = BASE_DIR / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_CSV = OUT_DIR / "church_history_dataset.csv"


# =========================================================
# CURATED CHURCH HISTORY EVENTS
# Format: (month, day, year, summary, category, source_note)
#
# Categories:
#   papacy        — papal elections, deaths, key papal acts
#   council       — ecumenical councils
#   dogma         — dogmatic definitions
#   saint         — canonisations, beatifications, key saints
#   martyrdom     — martyrs and persecutions
#   apparition    — Marian apparitions
#   evangelisation— missionary milestones
#   reform        — Church reforms and milestones
#   liturgy       — liturgical history
# =========================================================

EVENTS = [

    # =====================================================
    # JANUARY
    # =====================================================
    (1,  1,    1,  "The Solemnity of Mary, Mother of God, has been celebrated on January 1 "
                   "since the early Church, honouring the Theotokos — God-bearer — "
                   "as proclaimed at the Council of Ephesus in 431.",
                   "apparition", "General Roman Calendar"),
    (1,  3,  1962, "Pope John XXIII excommunicates Fidel Castro after the Cuban government "
                   "expels all foreign-born priests and restricts the Church.",
                   "papacy", "Vatican Records"),
    (1,  6,   490, "The feast of the Epiphany, one of the oldest feasts of the Church, "
                   "commemorates the visit of the Magi to the Christ Child — "
                   "the first manifestation of Christ to the Gentile world.",
                   "liturgy", "General Roman Calendar"),
    (1, 17,   356, "St Anthony of Egypt, Father of Christian monasticism, dies at age 105. "
                   "His life, written by St Athanasius, inspired thousands to embrace "
                   "the monastic life and shaped the entire tradition of Christian asceticism.",
                   "saint", "Butler's Lives of the Saints"),
    (1, 28,  1225, "St Thomas Aquinas is born in Roccasecca, Italy. He would become "
                   "the Church's greatest theologian, whose Summa Theologica remains "
                   "the foundation of Catholic philosophical and theological thought.",
                   "saint", "Butler's Lives of the Saints"),

    # =====================================================
    # FEBRUARY
    # =====================================================
    (2,  2,   484, "The Feast of the Presentation of the Lord (Candlemas) is one of "
                   "the most ancient feasts of the Church, celebrating the presentation "
                   "of the infant Jesus in the Temple and the purification of Mary.",
                   "liturgy", "General Roman Calendar"),
    (2, 11,  1858, "Our Lady appears for the first time to St Bernadette Soubirous "
                   "at the grotto of Massabielle in Lourdes, France. "
                   "She would appear 18 times in total, and Lourdes became one of "
                   "the greatest pilgrimage sites in the world.",
                   "apparition", "Approved by Bishop Laurence of Tarbes, 1862"),
    (2, 11,  1929, "The Lateran Treaty is signed between the Holy See and Italy, "
                   "establishing Vatican City as an independent sovereign state "
                   "and ending the 'Roman Question' that had persisted since 1870.",
                   "papacy", "Vatican Archives"),
    (2, 16,  2022, "Pope Emeritus Benedict XVI celebrates his 95th birthday — "
                   "the longest-lived pope in history. He resigned in 2013 "
                   "after a pontificate marked by profound theological teaching "
                   "and a courageous defence of the faith.",
                   "papacy", "Vatican News"),
    (2, 22,   258, "St Peter's Chair is celebrated — the feast commemorating "
                   "St Peter's episcopal authority, given directly by Christ, "
                   "as the foundation of the Church's unity.",
                   "liturgy", "General Roman Calendar"),

    # =====================================================
    # MARCH
    # =====================================================
    (3,  7,   203, "St Perpetua and St Felicitas are martyred in Carthage. "
                   "Perpetua's prison diary, which she wrote herself, is one of "
                   "the earliest Christian documents written by a woman "
                   "and one of the most moving accounts of martyrdom in history.",
                   "martyrdom", "Acta Sanctorum"),
    (3, 17,   461, "St Patrick, Apostle of Ireland, dies. Having been enslaved "
                   "as a youth and then escaping, he returned to Ireland as a bishop "
                   "and evangelised the island, establishing the Church there "
                   "through decades of missionary work.",
                   "evangelisation", "Butler's Lives of the Saints"),
    (3, 25,   431, "The Council of Ephesus begins, ultimately defining Mary "
                   "as Theotokos — Mother of God — against the Nestorian heresy. "
                   "This is one of the most significant Marian dogmatic events "
                   "in Church history.",
                   "council", "Conciliar Documents"),
    (3, 25,     0, "The Annunciation of the Lord: the Angel Gabriel announces to Mary "
                   "that she will conceive and bear the Son of God. "
                   "The Church has celebrated this solemnity on March 25 "
                   "since at least the 5th century.",
                   "liturgy", "General Roman Calendar"),

    # =====================================================
    # APRIL
    # =====================================================
    (4,  2,  2005, "Pope John Paul II dies at the Vatican at 9:37 PM. "
                   "His 26-year pontificate transformed the Church and the world. "
                   "He was beatified in 2011 and canonised in 2014.",
                   "papacy", "Vatican Records"),
    (4, 19,  2005, "Cardinal Joseph Ratzinger is elected Pope Benedict XVI "
                   "on the second day of the conclave. "
                   "He takes the name Benedict in honour of St Benedict of Nursia "
                   "and Pope Benedict XV, the great pope of peace.",
                   "papacy", "Vatican Records"),
    (4, 23,   303, "St George, martyr, is executed under the persecution of Diocletian. "
                   "He became one of the most venerated martyrs in both East and West, "
                   "a symbol of Christian courage in the face of tyranny.",
                   "martyrdom", "Butler's Lives of the Saints"),
    (4, 27,  2014, "Pope John Paul II and Pope John XXIII are canonised together "
                   "by Pope Francis in St Peter's Square before a crowd of over "
                   "800,000 pilgrims — one of the largest canonisation Masses in history.",
                   "saint", "Vatican News"),

    # =====================================================
    # MAY
    # =====================================================
    (5,  1,  2011, "Pope Benedict XVI beatifies Pope John Paul II "
                   "before more than one million faithful in St Peter's Square — "
                   "the fastest beatification process in modern Church history.",
                   "saint", "Vatican News"),
    (5, 13,  1917, "Our Lady appears for the first time to three shepherd children — "
                   "Lucia, Francisco, and Jacinta — at the Cova da Iria in Fatima, Portugal. "
                   "She would appear on the 13th of each month until October, "
                   "delivering a message of prayer, penance, and consecration.",
                   "apparition", "Approved by Bishop of Leiria, 1930"),
    (5, 13,  1981, "Pope John Paul II is shot and critically wounded in St Peter's Square "
                   "by Mehmet Ali Agca. He later attributed his survival to the intercession "
                   "of Our Lady of Fatima, and donated the bullet to the Fatima shrine.",
                   "papacy", "Vatican Records"),
    (5, 20,  1506, "Christopher Columbus dies in Valladolid, Spain. "
                   "His voyages opened the New World to the Gospel, and he sailed "
                   "under the patronage of the Catholic monarchs Ferdinand and Isabella.",
                   "evangelisation", "Historical Records"),
    (5, 26,  1828, "Pope Leo XII canonises Alphonsus Liguori, founder of the Redemptorists "
                   "and Doctor of the Church. St Alphonsus was one of the most prolific "
                   "writers in Church history and a giant of moral theology.",
                   "saint", "Vatican Archives"),
    (5, 31,     0, "The Feast of the Visitation of the Blessed Virgin Mary: "
                   "Mary visits her cousin Elizabeth, who greets her as "
                   "the Mother of my Lord. This is the occasion of the Magnificat, "
                   "one of the greatest prayers in Scripture.",
                   "liturgy", "General Roman Calendar"),

    # =====================================================
    # JUNE
    # =====================================================
    (6, 11,  1963, "Pope John XXIII dies. He had opened the Second Vatican Council "
                   "and was beloved for his warmth and pastoral heart. "
                   "He would be canonised alongside John Paul II in 2014.",
                   "papacy", "Vatican Records"),
    (6, 13,  1231, "St Anthony of Padua dies at age 35. One of the most beloved saints "
                   "in the Church, he was canonised less than a year after his death "
                   "and declared a Doctor of the Church in 1946.",
                   "saint", "Butler's Lives of the Saints"),
    (6, 19,  1991, "Pope John Paul II beatifies 108 Polish martyrs of World War II, "
                   "witnesses who gave their lives rather than renounce their faith "
                   "under Nazi occupation.",
                   "martyrdom", "Vatican Records"),
    (6, 21,  1591, "St Aloysius Gonzaga dies at age 23 while caring for plague victims "
                   "in Rome. He is the patron of Catholic youth and students, "
                   "renowned for his extraordinary purity and dedication to prayer.",
                   "saint", "Butler's Lives of the Saints"),
    (6, 24,     0, "The Nativity of St John the Baptist — one of only three birthdays "
                   "celebrated in the Roman Calendar (along with Christ and Mary). "
                   "John was the last prophet, the voice crying in the wilderness, "
                   "and the one chosen to baptise the Lord.",
                   "liturgy", "General Roman Calendar"),
    (6, 29,     0, "The Solemnity of Saints Peter and Paul: the two great pillars "
                   "of the Church, both martyred in Rome under Nero. "
                   "This feast has been celebrated in Rome since at least the 3rd century.",
                   "martyrdom", "General Roman Calendar"),

    # =====================================================
    # JULY
    # =====================================================
    (7,  6,  1535, "St Thomas More is executed on Tower Hill, London, "
                   "after refusing to accept King Henry VIII as Supreme Head of the Church. "
                   "His last words: I die the King's good servant, but God's first.",
                   "martyrdom", "Acts of the English Martyrs"),
    (7, 11,   543, "The death of St Benedict of Nursia, Father of Western Monasticism. "
                   "His Rule became the foundation of monastic life in the West "
                   "and shaped the culture of medieval Europe.",
                   "saint", "Butler's Lives of the Saints"),
    (7, 16,  1251, "Our Lady of Mount Carmel: tradition holds that the Blessed Virgin "
                   "appeared to St Simon Stock and gave him the Brown Scapular "
                   "as a sign of her special protection. "
                   "The feast has been celebrated on July 16 since the 16th century.",
                   "apparition", "Carmelite Tradition"),
    (7, 22,     0, "The feast of St Mary Magdalene — Apostle to the Apostles — "
                   "the first witness of the Resurrection. Pope Francis elevated "
                   "her commemoration to a feast in 2016, honouring her unique role "
                   "in salvation history.",
                   "saint", "General Roman Calendar"),
    (7, 25,     0, "The feast of St James the Apostle, one of the Twelve, "
                   "martyred by Herod Agrippa around 44 AD — the first apostle to die "
                   "for Christ. His shrine at Santiago de Compostela has drawn "
                   "pilgrims for over a thousand years.",
                   "saint", "General Roman Calendar"),

    # =====================================================
    # AUGUST
    # =====================================================
    (8,  4,  1859, "St John Vianney, the Curé of Ars, dies. "
                   "For over forty years he spent up to 18 hours a day in the confessional, "
                   "drawing pilgrims from across Europe. He is the patron saint of priests.",
                   "saint", "Butler's Lives of the Saints"),
    (8,  9,  1942, "St Teresa Benedicta of the Cross (Edith Stein) is killed "
                   "in the gas chambers of Auschwitz. A Jewish philosopher who converted "
                   "to Catholicism and became a Carmelite nun, she is co-patron of Europe.",
                   "martyrdom", "Vatican Records"),
    (8, 14,  1941, "St Maximilian Kolbe offers his life in exchange for a fellow prisoner "
                   "in Auschwitz. He dies after two weeks of starvation. "
                   "Pope John Paul II, who knew him, canonised him in 1982.",
                   "martyrdom", "Vatican Records"),
    (8, 15,   431, "The Dormition and Assumption of the Blessed Virgin Mary "
                   "has been celebrated on August 15 since at least the 5th century. "
                   "It was defined as a dogma by Pope Pius XII in 1950 "
                   "in the apostolic constitution Munificentissimus Deus.",
                   "dogma", "Munificentissimus Deus, 1950"),
    (8, 28,   430, "St Augustine of Hippo dies in Hippo Regius as the Vandals besiege "
                   "the city. His Confessions and The City of God remain two of "
                   "the greatest works in Christian intellectual history.",
                   "saint", "Butler's Lives of the Saints"),

    # =====================================================
    # SEPTEMBER
    # =====================================================
    (9,  3,  1914, "Cardinal Giacomo della Chiesa is elected Pope Benedict XV "
                   "at the outbreak of World War I. His tireless peace efforts "
                   "and charitable works for prisoners and refugees earned him "
                   "the title Father of the Poor.",
                   "papacy", "Vatican Archives"),
    (9, 13,  1321, "Dante Alighieri dies in Ravenna. His Divine Comedy — "
                   "Inferno, Purgatorio, Paradiso — is the greatest work of Catholic "
                   "literature and a profound meditation on sin, redemption, and glory.",
                   "saint", "Historical Records"),
    (9, 14,   629, "The Exaltation of the Holy Cross: the feast commemorates "
                   "the recovery of the True Cross by Emperor Heraclius "
                   "and its return to Jerusalem. One of the oldest feasts of the Church.",
                   "liturgy", "General Roman Calendar"),
    (9, 27,  1540, "Pope Paul III formally approves the Society of Jesus (Jesuits), "
                   "founded by St Ignatius of Loyola. "
                   "The Jesuits would become the greatest missionary order in history, "
                   "bringing the faith to Asia, the Americas, and Africa.",
                   "evangelisation", "Regimini militantis Ecclesiae, 1540"),
    (9, 29,     0, "The feast of Saints Michael, Gabriel, and Raphael, Archangels — "
                   "the great princes of the heavenly host. "
                   "St Michael, defender of the Church, was invoked by Leo XIII "
                   "who composed the famous Prayer to St Michael after Mass.",
                   "liturgy", "General Roman Calendar"),

    # =====================================================
    # OCTOBER
    # =====================================================
    (10,  2,     0, "The feast of the Guardian Angels: the Church teaches that "
                    "God assigns a guardian angel to every soul. "
                    "This feast was extended to the universal Church by Pope Paul V in 1608.",
                    "liturgy", "General Roman Calendar"),
    (10,  7,  1571, "The Battle of Lepanto: the Christian fleet defeats the Ottoman navy, "
                    "widely attributed to the intercession of Our Lady of the Rosary. "
                    "Pope Pius V had called all of Europe to pray the Rosary. "
                    "October 7 became the feast of Our Lady of the Rosary.",
                    "apparition", "Historical Records / General Roman Calendar"),
    (10, 11,  1962, "Pope John XXIII opens the Second Vatican Council — "
                    "the 21st Ecumenical Council of the Church — "
                    "with the famous words: the Church is not a museum of old things "
                    "but a living fountain.",
                    "council", "Vatican Archives"),
    (10, 13,  1917, "The Miracle of the Sun at Fatima: approximately 70,000 witnesses "
                    "see the sun spin and plunge toward the earth before returning "
                    "to its place. Our Lady appears for the sixth and final time "
                    "to the three shepherd children.",
                    "apparition", "Documented by secular and religious press, 1917"),
    (10, 16,  1978, "Cardinal Karol Wojtyla of Krakow is elected Pope John Paul II — "
                    "the first non-Italian pope in 455 years and the first Polish pope ever. "
                    "His pontificate of 26 years would be one of the most consequential "
                    "in modern history.",
                    "papacy", "Vatican Records"),
    (10, 22,  1978, "Pope John Paul II is inaugurated. His opening words — "
                    "Be not afraid! Open, indeed, fling open the doors to Christ — "
                    "set the tone for a pontificate that would help bring down "
                    "communism and revitalise the Church.",
                    "papacy", "Vatican Records"),
    (10, 28,    61, "The feast of Saints Simon and Jude, Apostles. "
                    "Both were among the Twelve chosen by Christ. "
                    "St Jude, often called the patron of hopeless causes, "
                    "is one of the most widely invoked saints in popular piety.",
                    "saint", "General Roman Calendar"),

    # =====================================================
    # NOVEMBER
    # =====================================================
    (11,  1,   835, "The Feast of All Saints is celebrated universally for the first time "
                    "on November 1 by decree of Pope Gregory IV. "
                    "It honours all the saints in heaven, known and unknown.",
                    "liturgy", "Historical Records"),
    (11,  2,  1000, "The Commemoration of All Souls has been observed on November 2 "
                    "since St Odilo of Cluny extended it to the whole Church around 998. "
                    "It expresses the Church's faith in purgatory and the power of prayer "
                    "for the dead.",
                    "liturgy", "Historical Records"),
    (11, 18,  1302, "Pope Boniface VIII issues Unam Sanctam, one of the strongest "
                    "assertions of papal authority in history, declaring that "
                    "submission to the Roman Pontiff is absolutely necessary for salvation.",
                    "papacy", "Vatican Archives"),
    (11, 18,  1626, "St Peter's Basilica in Rome is consecrated by Pope Urban VIII, "
                    "120 years after construction began under Pope Julius II. "
                    "It is the largest church in the world and the centre "
                    "of Catholic Christendom.",
                    "liturgy", "Vatican Archives"),
    (11, 21,  1964, "Pope Paul VI promulgates Lumen Gentium — the Dogmatic Constitution "
                    "on the Church — the central document of the Second Vatican Council, "
                    "which defines the Church as the People of God "
                    "and the mystery of communion.",
                    "council", "Lumen Gentium, Vatican II"),

    # =====================================================
    # DECEMBER
    # =====================================================
    (12,  3,  1552, "St Francis Xavier, the greatest missionary since St Paul, dies "
                    "on the island of Sancian off the coast of China "
                    "as he prepared to enter the country to preach the Gospel. "
                    "He had baptised hundreds of thousands across India, Japan, and Asia.",
                    "evangelisation", "Butler's Lives of the Saints"),
    (12,  8,  1854, "Pope Pius IX defines the Dogma of the Immaculate Conception "
                    "in the apostolic constitution Ineffabilis Deus — "
                    "that Mary was preserved from all stain of original sin "
                    "from the first moment of her conception.",
                    "dogma", "Ineffabilis Deus, 1854"),
    (12,  9,  1531, "Our Lady of Guadalupe appears to St Juan Diego on Tepeyac Hill "
                    "near Mexico City. She asks for a church to be built there "
                    "and leaves her image miraculously imprinted on his tilma. "
                    "Within seven years, nine million indigenous people converted to "
                    "the faith.",
                    "apparition", "Approved by Bishop Juan de Zumárraga, 1531"),
    (12, 25,     0, "The Nativity of Our Lord Jesus Christ: the celebration of Christmas "
                    "on December 25 is attested in Rome from at least 336 AD. "
                    "It is the central mystery of the Incarnation — "
                    "God becoming man to save mankind.",
                    "liturgy", "General Roman Calendar"),
    (12, 31,  2022, "Pope Emeritus Benedict XVI dies at the Mater Ecclesiae Monastery "
                    "in Vatican City at the age of 95. "
                    "He was the first pope to resign since Gregory XII in 1415 "
                    "and leaves a vast theological legacy for the Church.",
                    "papacy", "Vatican News"),
]


# =========================================================
# HELPERS
# =========================================================
def make_id(text: str) -> str:
    return hashlib.md5(" ".join(text.lower().split()).encode()).hexdigest()


def make_title(category: str, month: int, day: int, year: int) -> str:
    category_titles = {
        "papacy":         "Papal History",
        "council":        "Church Council",
        "dogma":          "Dogmatic Definition",
        "saint":          "Saint of the Church",
        "martyrdom":      "Martyrs of the Faith",
        "apparition":     "Marian Apparition",
        "evangelisation": "Evangelisation",
        "reform":         "Church Reform",
        "liturgy":        "Liturgical History",
    }
    label = category_titles.get(category, "Church History")
    year_str = f"{abs(year)} {'BC' if year < 0 else 'AD'}" if year != 0 else ""
    if year_str:
        return f"{label} — {month:02d}/{day:02d}/{year_str}"
    return f"{label} — {month:02d}/{day:02d}"


CATEGORY_SEASON_TAGS = {
    "papacy":         "general",
    "council":        "general",
    "dogma":          "general",
    "saint":          "general",
    "martyrdom":      "general",
    "apparition":     "may,october,marian_feast",
    "evangelisation": "general",
    "reform":         "general",
    "liturgy":        "general",
}


# =========================================================
# BUILD
# =========================================================
def build_rows() -> list[dict]:
    rows = []
    seen: set[str] = set()

    for month, day, year, summary, category, source_note in EVENTS:
        summary = " ".join(summary.split()).strip()
        qid = make_id(summary)

        if qid in seen:
            continue
        seen.add(qid)

        rows.append({
            "id":          qid,
            "title":       make_title(category, month, day, year),
            "summary":     summary,
            "month":       month,
            "day":         day,
            "year":        year,
            "month_day":   f"{month:02d}-{day:02d}",
            "category":    category,
            "source_note": source_note,
            "season_tags": CATEGORY_SEASON_TAGS.get(category, "general"),
            "topic":       "church",
            "dataset":     "church_history",
            "confidence":  9,
            "risk":        1,
            "status":      "ready",
        })

    return rows


def write_csv(rows: list[dict]) -> None:
    fieldnames = [
        "id", "title", "summary", "month", "day", "year", "month_day",
        "category", "source_note", "season_tags", "topic", "dataset",
        "confidence", "risk", "status"
    ]
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    print("[INFO] Building Church History dataset...")
    rows = build_rows()

    from collections import Counter
    cats = Counter(r["category"] for r in rows)

    print(f"\n  Total events: {len(rows)}")
    print("\n  By category:")
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"    {cat:<20s} {count:3d}")

    months = Counter(r["month"] for r in rows)
    print("\n  By month:")
    month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sep","Oct","Nov","Dec"]
    for m in range(1, 13):
        bar = "█" * months.get(m, 0)
        print(f"    {month_names[m-1]}  {months.get(m,0):2d}  {bar}")

    write_csv(rows)
    print(f"\n  ✅ Saved → {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
