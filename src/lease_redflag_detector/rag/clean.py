"""Cleaning and normalization of extracted blocks, and pseudonymization of contracts.

Extraction already drops what is page furniture in each format (running headers and
footers, page numbers, site menus, editorial notes of the legislation database). This
module normalizes the remaining text:

- Unicode NFC; non-breaking and zero-width spaces, soft hyphens and BOMs removed;
- Latin letters that OCR put into Cyrillic words ("OPEHДA") replaced by the Cyrillic
  letters they look like. In scanned contracts OCR also reads whole words as Latin
  ("CTOPIH", "TOBAPHCTBO", with "H" for both "Н" and "И"): such a word is replaced only
  when one of its Cyrillic readings is a word of the corpus vocabulary, so real Latin
  words ("UA", "IBAN", "IX") stay as they are;
- blocks that are OCR noise from stamps and signatures ("Ї, 22h pany) pS") dropped.

Pseudonymization replaces the surnames of people with other surnames of the same
ending and masks e-mail addresses, phone numbers, IBANs and individual tax numbers.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from itertools import product
from math import prod

from lease_redflag_detector.rag.document import Block

INVISIBLE = re.compile(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff]")
SPACES = re.compile(r"[\u00a0\u2007\u202f\t ]+")
# Latin letters OCR confuses with Cyrillic ones of the same shape.
LOOKALIKES = str.maketrans(
    "AaBCcEeHIiKMOoPpTXxyY",
    "АаВСсЕеНІіКМОоРрТХхуУ",
)
# The Cyrillic letters OCR reads as each Latin one, the likeliest first.
OCR_READINGS = {
    "A": "АЯ", "B": "ВБ", "C": "С", "E": "ЕЄ", "H": "НИ", "I": "ІЇ", "K": "К",
    "M": "М", "O": "О", "P": "Р", "T": "Т", "U": "И", "X": "Х", "Y": "У",
    "a": "а", "c": "с", "d": "д", "e": "еє", "i": "ії", "k": "к", "m": "тм",
    "n": "п", "o": "о", "p": "р", "r": "г", "u": "и", "x": "хк", "y": "у",
}  # fmt: skip
MAX_READINGS = 256
ROMAN = re.compile(r"^[IVXLCDM]+$")
WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
CYRILLIC = re.compile(r"[а-яіїєґА-ЯІЇЄҐ]")
LATIN = re.compile(r"[a-zA-Z]")


def vocabulary(texts: Iterable[str], min_count: int = 2) -> set[str]:
    """Cyrillic words of a corpus, casefolded, that occur at least `min_count` times."""
    counts = Counter(
        word.casefold()
        for text in texts
        for word in WORD.findall(text)
        if CYRILLIC.search(word) and not LATIN.search(word)
    )
    return {word for word, n in counts.items() if n >= min_count}


def cyrillic_readings(word: str) -> list[str]:
    options = [OCR_READINGS.get(ch, ch) for ch in word]
    if prod(len(option) for option in options) > MAX_READINGS:
        return []
    return ["".join(letters) for letters in product(*options)]


def fix_case(word: str) -> str:
    """OCR reads a lowercase "т" or "н" as a capital T or H: "ВарТосТі" → "Вартості"."""
    return word if word.isupper() else word[0] + word[1:].lower()


# Share of letters OCR never reads Cyrillic as above which a Latin word is English
# ("Convention" 0.2) rather than a misread one ("POSPAXYHKY" 0.1, "Opendodasya" 0.09).
ENGLISH_SHARE = 0.15


def is_english(word: str) -> bool:
    if CYRILLIC.search(word):
        return False
    foreign = sum(bool(LATIN.match(ch)) and ch not in OCR_READINGS for ch in word)
    return foreign / len(word) > ENGLISH_SHARE


def fix_script(text: str, words: set[str] | None = None) -> str:
    """Replace Latin look-alikes in Cyrillic words; with a vocabulary `words`, also in
    fully Latin words that read as one of its words, unless they stand next to an
    English word ("Convention on Combating")."""
    matches = list(WORD.finditer(text))
    english = [is_english(m.group(0)) for m in matches]
    pieces, end = [], 0
    for i, match in enumerate(matches):
        word = match.group(0)
        pieces.append(text[end : match.start()])
        end = match.end()
        if not LATIN.search(word):
            pieces.append(word)
            continue
        mixed = bool(CYRILLIC.search(word))
        in_english = (i > 0 and english[i - 1]) or (
            i + 1 < len(matches) and english[i + 1]
        )
        fixed = word.translate(LOOKALIKES) if mixed else word
        if words and (
            mixed or (len(word) >= 2 and not ROMAN.match(word) and not in_english)
        ):
            for reading in cyrillic_readings(word):
                if reading.casefold() in words:
                    fixed = fix_case(reading)
                    break
        pieces.append(fixed)
    pieces.append(text[end:])
    return "".join(pieces)


def normalize(text: str, words: set[str] | None = None) -> str:
    text = unicodedata.normalize("NFC", text)
    text = INVISIBLE.sub("", text)
    text = fix_script(text, words)
    return SPACES.sub(" ", text).strip()


def is_noise(block: Block) -> bool:
    """A paragraph with no real words: OCR of a stamp, a signature or a scan edge."""
    if block.kind != "paragraph":
        return False
    words = [w for w in WORD.findall(block.text) if len(w) >= 3]
    real = [w for w in words if CYRILLIC.search(w) and not LATIN.search(w)]
    return len(real) < 2 and len(block.text) < 80


def clean_blocks(blocks: list[Block], words: set[str] | None = None) -> list[Block]:
    """Normalize blocks and drop noise; `words` is the vocabulary for `fix_script`."""
    cleaned = []
    for block in blocks:
        block.text = normalize(block.text, words)
        block.rows = [[normalize(cell, words) for cell in row] for row in block.rows]
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
