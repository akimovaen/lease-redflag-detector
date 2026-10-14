"""Build the lease text dataset from the ALeaseBERT annotations.

Selects leases for group A (plain text) and group B (OCR scans, built later),
converts group A to text files and writes data/texts/manifest.csv.

The `dirt` column combines automatic heuristics with manual corrections from
data/texts/dirt_manual.csv (columns: id, add, remove; tags separated by ";").

Usage: uv run python scripts/build_dataset.py
"""

import csv
import itertools
import json
import random
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POOL = ROOT / "data/raw/aleasebert/annotated/pool"
TEXTS = ROOT / "data/texts"
MANIFEST = TEXTS / "manifest.csv"
DIRT_MANUAL = TEXTS / "dirt_manual.csv"

SEED = 42
MAX_WORDS = 10_000
MIN_MVP_FLAGS = 3
MVP_FLAGS = {
    "break_option",
    "services_charges",
    "sublease_permitted",
    "reinstatement_clause",
    "landlord_repairs",
}
REDFLAG_CLASS = "e_23"
REDFLAG_TYPE_FIELD = "f_24"

# (min_words, max_words) -> how many leases to pick for each group
BUCKETS = {
    (0, 2_000): {"A": 4, "B": 2},
    (2_000, 5_000): {"A": 5, "B": 3},
    (5_000, MAX_WORDS + 1): {"A": 6, "B": 0},
}

DIRT_TAGS = {
    "ocr",  # went through OCR (group B)
    "mixed_lang",  # contains fragments in another language
    "broken_layout",  # sentences split across lines
    "template_blanks",  # unfilled fields like ___ or [ ]
    "encoding",  # broken characters: mojibake, Wingdings checkboxes as þ/ü
    "translated",  # non-native English of a translation (manual only)
    "missing_fields",  # schema fields absent from the lease (from golden set)
}
# Thresholds calibrated on group A: clean texts stay below them.
MIN_FOREIGN_WORDS = 3
MIN_MID_BREAK_SHARE = 0.05
NON_LATIN_SCRIPT = re.compile(r"[Ѐ-ӿ؀-ۿ぀-ヿ一-鿿]")
TEMPLATE_BLANK = re.compile(r"_{3,}|\[\s*\]")
# U+FFFD replacement char, UTF-8 read as Latin-1 (Ã©, â€™), or a lone Wingdings
# checkbox/checkmark glyph rendered as a Latin-1 letter (þ, ü, ý, ¨).
BROKEN_ENCODING = re.compile(r"�|Ã[\u0080-¿]|â€|(?<!\w)[þüý¨](?!\w)")
LIST_MARKER = re.compile(r"\(?([ivxlcdm]+|[a-z]|\d+(\.\d+)*)[.)]?|-\d+-", re.IGNORECASE)
LINE_END = re.compile(r"[.:;!?,)]$")

MANIFEST_FIELDS = [
    "id",
    "group",
    "source",
    "source_id",
    "language",
    "words",
    "mvp_flags",
    "dirt",
    "license",
    "golden",
]


@dataclass
class Lease:
    source_id: str
    html_path: Path
    paragraphs: list[str]
    mvp_flags: set[str]

    @property
    def words(self) -> int:
        return sum(len(p.split()) for p in self.paragraphs)


class ParagraphParser(HTMLParser):
    """Collects the text of each <p> element, in document order."""

    def __init__(self) -> None:
        super().__init__()
        self.paragraphs: list[str] = []
        self._current: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "p":
            self._current = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "p" and self._current is not None:
            self.paragraphs.append("".join(self._current).strip())
            self._current = None

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current.append(data)


def load_lease(ann_path: Path) -> Lease:
    html_path = ann_path.with_name(ann_path.name.replace(".ann.json", ".plain.html"))
    parser = ParagraphParser()
    parser.feed(html_path.read_text(encoding="utf-8"))

    annotations = json.loads(ann_path.read_text(encoding="utf-8"))
    flag_types = {
        entity["fields"].get(REDFLAG_TYPE_FIELD, {}).get("value")
        for entity in annotations["entities"]
        if entity["classId"] == REDFLAG_CLASS
    }
    source_id = ann_path.name.split("-", 1)[1].removesuffix(".ann.json")
    return Lease(source_id, html_path, parser.paragraphs, flag_types & MVP_FLAGS)


def detect_dirt(paragraphs: list[str]) -> set[str]:
    text = "\n".join(paragraphs)
    tags = set()

    foreign_words = {
        word
        for word in re.findall(r"\w+", text)
        if any(char.isalpha() and not char.isascii() for char in word)
    }
    if len(foreign_words) >= MIN_FOREIGN_WORDS or NON_LATIN_SCRIPT.search(text):
        tags.add("mixed_lang")

    lines = [line.strip() for line in paragraphs if line.strip()]
    mid_breaks = sum(
        1
        for line, next_line in itertools.pairwise(lines)
        if not LIST_MARKER.fullmatch(line)
        and not LINE_END.search(line)
        and next_line[:1].islower()
    )
    if lines and mid_breaks / len(lines) >= MIN_MID_BREAK_SHARE:
        tags.add("broken_layout")

    if TEMPLATE_BLANK.search(text):
        tags.add("template_blanks")
    if BROKEN_ENCODING.search(text):
        tags.add("encoding")
    return tags


def load_manual_dirt() -> dict[str, tuple[set[str], set[str]]]:
    """Returns {text id: (tags to add, tags to remove)}."""
    if not DIRT_MANUAL.exists():
        return {}
    manual = {}
    with DIRT_MANUAL.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            add, remove = (
                {tag.strip() for tag in row[column].split(";") if tag.strip()}
                for column in ("add", "remove")
            )
            unknown = (add | remove) - DIRT_TAGS
            if unknown:
                raise ValueError(
                    f"{DIRT_MANUAL.name}: unknown tags {unknown} for {row['id']}"
                )
            manual[row["id"]] = (add, remove)
    return manual


def select(leases: list[Lease]) -> dict[str, list[Lease]]:
    candidates = sorted(
        (
            lease
            for lease in leases
            if lease.words <= MAX_WORDS and len(lease.mvp_flags) >= MIN_MVP_FLAGS
        ),
        key=lambda lease: lease.source_id,
    )
    rng = random.Random(SEED)
    picked: dict[str, list[Lease]] = {"A": [], "B": []}
    for (low, high), counts in BUCKETS.items():
        bucket = [lease for lease in candidates if low <= lease.words < high]
        sample = rng.sample(bucket, counts["A"] + counts["B"])
        picked["A"] += sample[: counts["A"]]
        picked["B"] += sample[counts["A"] :]
    return picked


def main() -> None:
    leases = [load_lease(path) for path in sorted(POOL.glob("*.ann.json"))]
    picked = select(leases)
    manual_dirt = load_manual_dirt()

    TEXTS.mkdir(parents=True, exist_ok=True)
    rows = []
    for lease in picked["A"]:
        text_id = f"alb_{lease.source_id}"
        add, remove = manual_dirt.get(text_id, (set(), set()))
        dirt = (detect_dirt(lease.paragraphs) | add) - remove
        (TEXTS / f"{text_id}.txt").write_text(
            "\n".join(lease.paragraphs) + "\n", encoding="utf-8"
        )
        rows.append(
            {
                "id": text_id,
                "group": "A",
                "source": "ALeaseBERT",
                "source_id": lease.source_id,
                "language": "en",
                "words": lease.words,
                "mvp_flags": ";".join(sorted(lease.mvp_flags)),
                "dirt": ";".join(sorted(dirt)),
                "license": "CC BY-NC 4.0",
                "golden": "",
            }
        )

    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Group A: wrote {len(rows)} texts to {TEXTS.relative_to(ROOT)}")
    print("Group B (OCR, not built yet):")
    for lease in picked["B"]:
        print(f"  {lease.source_id} ({lease.words} words)")


if __name__ == "__main__":
    main()
