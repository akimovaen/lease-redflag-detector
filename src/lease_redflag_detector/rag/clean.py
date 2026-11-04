"""Cleaning and normalization of extracted blocks, and pseudonymization of contracts.

Extraction already drops what is page furniture in each format (running headers and
footers, page numbers, site menus, editorial notes of the legislation database). This
module normalizes the remaining text:

- Unicode NFC; non-breaking and zero-width spaces, soft hyphens and BOMs removed;
- Latin letters that OCR put into Cyrillic words ("OPEHДA") replaced by the Cyrillic
  letters they look like. Only words that mix both scripts are touched, so real Latin
  words ("UA", "CPI") and fully misread ones stay as they are;
- blocks that are OCR noise from stamps and signatures ("Ї, 22h pany) pS") dropped.

Pseudonymization replaces the surnames of people with other surnames of the same
ending and masks e-mail addresses, phone numbers, IBANs and individual tax numbers.
"""

import re
import unicodedata

from lease_redflag_detector.rag.document import Block

INVISIBLE = re.compile(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff]")
SPACES = re.compile(r"[\u00a0\u2007\u202f\t ]+")
# Latin letters OCR confuses with Cyrillic ones of the same shape.
LOOKALIKES = str.maketrans(
    "AaBCcEeHIiKMOoPpTXxyY",
    "АаВСсЕеНІіКМОоРрТХхуУ",
)
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
CYRILLIC = re.compile(r"[а-яіїєґА-ЯІЇЄҐ]")
LATIN = re.compile(r"[a-zA-Z]")


def fix_mixed_script(text: str) -> str:
    def fix(match: re.Match) -> str:
        word = match.group(0)
        if CYRILLIC.search(word) and LATIN.search(word):
            return word.translate(LOOKALIKES)
        return word

    return WORD.sub(fix, text)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = INVISIBLE.sub("", text)
    text = fix_mixed_script(text)
    return SPACES.sub(" ", text).strip()


def is_noise(block: Block) -> bool:
    """A paragraph with no real words: OCR of a stamp, a signature or a scan edge."""
    if block.kind != "paragraph":
        return False
    words = [w for w in WORD.findall(block.text) if len(w) >= 3]
    real = [w for w in words if CYRILLIC.search(w) and not LATIN.search(w)]
    return len(real) < 2 and len(block.text) < 80


def clean_blocks(blocks: list[Block]) -> list[Block]:
    cleaned = []
    for block in blocks:
        block.text = normalize(block.text)
        block.rows = [[normalize(cell) for cell in row] for row in block.rows]
        if block.text and not is_noise(block):
            cleaned.append(block)
    return cleaned


# Pseudonymization

PHONE = re.compile(
    r"(?<!\d)(\+?38)?[\s(]*0\d{2}[)\s-]*\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"
)
# Phone numbers OCR garbled (an extra digit, odd spacing) still follow a label.
LABELED_PHONE = re.compile(
    r"(?i)\b((?:тел|tel|ten|моб)\.?\s*:?\s*)\+?[\d()][\d\s()-]{8,}\d"
)
# A mobile number with a digit too many, as OCR sometimes reads it: "09111444787".
LONG_PHONE = re.compile(r"(?<!\d)(?:\+?38)?0\d{10}(?!\d)")
# OCR may put a space around "@".
EMAIL = re.compile(r"[\w.+-]+\s?@\s?[\w-]+\.[\w.-]+")
# OCR often reads the Latin "UA" of an IBAN as Cyrillic letters ("ЦА", "УА", "иА"),
# glues it to the "No" before it ("NoUA…") or breaks the digits ("…2600443* 81").
IBAN = re.compile(r"(?:UA|ЦА|УА|UА|иА)\s?(?:N[eo°]\s?)?\d{2}(?:[\s*]?\d){20,25}(?!\d)")
# A 10-digit individual tax number (RNOKPP); company codes (EDRPOU) have 8 digits.
TAX_NUMBER = re.compile(r"(?<!\d)\d{10}(?!\d)")


def pseudonymize(text: str, pseudonyms: dict[str, str]) -> str:
    """Replace surname stems and mask contact and bank details.

    Each stem also matches in capitals ("КУЖЕЛ"). All stems are replaced in one pass,
    longest first, so a replacement is never itself replaced by another entry.
    """
    if pseudonyms:
        table = dict(pseudonyms)
        for stem, replacement in pseudonyms.items():
            table.setdefault(stem.upper(), replacement.upper())
        stems = sorted(table, key=len, reverse=True)
        pattern = re.compile(rf"(?<!\w)({'|'.join(map(re.escape, stems))})(\w*)")
        text = pattern.sub(lambda m: table[m.group(1)] + m.group(2), text)
    text = EMAIL.sub("[email]", text)
    text = IBAN.sub("UA[IBAN]", text)
    text = LABELED_PHONE.sub(lambda m: m.group(1) + "[phone]", text)
    text = PHONE.sub("[phone]", text)
    text = LONG_PHONE.sub("[phone]", text)
    return TAX_NUMBER.sub("[tax number]", text)
