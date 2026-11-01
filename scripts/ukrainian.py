"""Group C of the dataset: Ukrainian leases.

Sources, all downloaded into data/raw/ (not committed):

- Signed lease contracts of state property from Prozorro.Sale, published as scans
  without a text layer (`scripts/fetch_prozorro.py`). Read with Tesseract OCR
  (`ukr+eng`); one contract per landlord, since each landlord uses its own template.
- Signed lease contracts of municipal property from Prozorro.Sale with a text layer,
  itself produced by the publisher's OCR.
- A lease template by the project author (data/raw/templates/).

Personal data is pseudonymized before a text is written: surnames listed in
data/raw/prozorro/pseudonyms.json are replaced by other surnames with the same
ending, and phone numbers, e-mail addresses, IBANs and individual tax numbers are
masked. The file stays out of git because it holds the real names.

OCR output is cached next to each PDF as text.txt.
"""

import json
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import scan
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PROZORRO = ROOT / "data/raw/prozorro"
TEMPLATES = ROOT / "data/raw/templates"
PSEUDONYMS = PROZORRO / "pseudonyms.json"

PROZORRO_LICENSE = "public information, published on Prozorro.Sale"
OCR_DPI = 300
MIN_TEXT_LAYER_WORDS = 100


@dataclass
class Source:
    text_id: str
    kind: str  # "scan", "text_layer" or "docx"
    path: Path
    source: str
    source_id: str
    license: str


SOURCES = [
    # Scans of state property leases, one per landlord.
    *(
        Source(
            f"uk_prz_{auction.rsplit('-', 1)[1]}",
            "scan",
            PROZORRO / auction / "contract.pdf",
            "Prozorro.Sale",
            auction,
            PROZORRO_LICENSE,
        )
        for auction in [
            "RLE001-UA-20251021-70422",  # PJSC Centrenergo
            "RLE001-UA-20251201-38360",  # JSC Ukrzaliznytsia
            "RLE001-UA-20251201-91885",  # a state research institute
            "RLE001-UA-20251113-29282",  # JSC Ukrposhta
            "RLE001-UA-20251211-60729",  # JSC Ukrnafta
            "RLE001-UA-20251215-41041",  # a private research institute
        ]
    ),
    # Municipal property leases with a text layer.
    *(
        Source(
            f"uk_prz_{document_id[:8]}",
            "text_layer",
            PROZORRO / f"doc-{document_id}" / "contract.pdf",
            "Prozorro.Sale",
            document_id,
            PROZORRO_LICENSE,
        )
        for document_id in [
            "ce9dfd295c7c41f79a5918e1230cdd3b",  # Chernivtsi, No. 42 of 2022
            "31134a620c094278ba5ba56d8364cffb",  # No. 564 of 2021
            "c9bfc288f1ab4c7692fcdb8bc0729520",  # No. 2_2026 of 2026
        ]
    ),
    Source(
        "uk_template",
        "docx",
        TEMPLATES / "ua_nonresidential_lease_template.docx",
        "project author",
        "ua_nonresidential_lease_template",
        "MIT",
    ),
]

PHONE = re.compile(
    r"(?<!\d)(\+?38)?[\s(]*0\d{2}[)\s-]*\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# OCR often reads the Latin "UA" of an IBAN as Cyrillic letters ("ЦА", "УА", "иА").
IBAN = re.compile(r"(?<!\w)(?:UA|ЦА|УА|UА|иА)\s?\d{2}(?:\s?\d){25}(?!\d)")
# A 10-digit individual tax number (RNOKPP); company codes (EDRPOU) have 8 digits.
TAX_NUMBER = re.compile(r"(?<!\d)\d{10}(?!\d)")


def pdf_text_layer(pdf: Path) -> str:
    result = subprocess.run(
        ["pdftotext", str(pdf), "-"], capture_output=True, check=True, text=True
    )
    return result.stdout


def ocr_pdf(pdf: Path) -> str:
    """OCR every page of a scanned PDF, cached as text.txt next to it."""
    cached = pdf.with_name("text.txt")
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    if shutil.which("pdftoppm") is None:
        raise RuntimeError("pdftoppm not found; install it with `brew install poppler`")
    pages_dir = pdf.with_name("pages")
    pages_dir.mkdir(exist_ok=True)
    subprocess.run(
        [
            "pdftoppm",
            "-r",
            str(OCR_DPI),
            "-gray",
            "-png",
            str(pdf),
            str(pages_dir / "p"),
        ],
        check=True,
    )
    text = "\n".join(
        scan.ocr(Image.open(page), lang="ukr+eng")
        for page in sorted(pages_dir.glob("p-*.png"))
    )
    shutil.rmtree(pages_dir)
    cached.write_text(text, encoding="utf-8")
    return text


def docx_text(path: Path) -> str:
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as docx:
        root = ElementTree.fromstring(docx.read("word/document.xml"))
    return "\n".join(
        "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        for paragraph in root.iter(f"{namespace}p")
    )


def raw_text(source: Source) -> str:
    if source.kind == "scan":
        return ocr_pdf(source.path)
    if source.kind == "text_layer":
        text = pdf_text_layer(source.path)
        if len(text.split()) < MIN_TEXT_LAYER_WORDS:
            raise ValueError(f"{source.path} has no usable text layer")
        return text
    return docx_text(source.path)


def load_pseudonyms() -> dict[str, str]:
    """Returns {surname stem: replacement stem}, longest stems first."""
    if not PSEUDONYMS.exists():
        return {}
    pairs = json.loads(PSEUDONYMS.read_text(encoding="utf-8"))
    return dict(sorted(pairs.items(), key=lambda pair: -len(pair[0])))


def pseudonymize(text: str, pseudonyms: dict[str, str]) -> str:
    for stem, replacement in pseudonyms.items():
        text = re.sub(
            rf"(?<!\w){re.escape(stem)}(\w*)",
            lambda m, r=replacement: r + m.group(1),
            text,
        )
    text = EMAIL.sub("[email]", text)
    text = IBAN.sub("UA[IBAN]", text)
    text = PHONE.sub("[phone]", text)
    return TAX_NUMBER.sub("[tax number]", text)


def clean(text: str) -> str:
    """Drops form feeds and runs of blank lines; keeps the line layout."""
    lines = [line.rstrip() for line in text.replace("\f", "\n").splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return text.strip() + "\n"


def texts() -> list[tuple[Source, str]]:
    pseudonyms = load_pseudonyms()
    return [
        (source, clean(pseudonymize(raw_text(source), pseudonyms)))
        for source in SOURCES
    ]
