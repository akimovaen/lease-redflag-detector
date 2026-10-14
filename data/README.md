# Data

Lease texts used to evaluate extraction, and the golden set they are scored against.

## Layout

```
data/
  texts/
    manifest.csv      # one row per text: source, language, length, dirt tags, license
    dirt_manual.csv   # manual corrections to the dirt tags
    *.txt             # the texts, one paragraph per line
  golden/             # hand-labeled reference outputs (to be added)
  processed/
  raw/                # original downloads, not committed
```

## Sources

### ALeaseBERT (group A)

Texts with the `alb_` prefix come from:

> Leivaditi, S., Rossi, J., Kanoulas, E. *ALeaseBERT: A Benchmark for Lease Contract Review.*
> University of Amsterdam. https://doi.org/10.21942/uva.19732993

Licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
They may be used for non-commercial purposes only, with attribution.
The [MIT License](../LICENSE) of this repository does **not** apply to them.

Changes made: a subset of 15 leases was selected, and each was converted from the
dataset's annotated HTML to plain text with one paragraph per line. The wording is unchanged.
Line N of a text corresponds to paragraph `s1pN` in the original annotations.

Selection: leases of at most 10,000 words that contain at least 3 of the 5 red flag types
used in this project (`break_option`, `services_charges`, `sublease_permitted`,
`reinstatement_clause`, `landlord_repairs`), sampled with a fixed seed across three
length buckets (under 2,000 / 2,000–5,000 / 5,000–10,000 words).

## Manifest

| Column | Meaning |
|---|---|
| `id` | file name without `.txt` |
| `group` | how the text was produced (A: ALeaseBERT plain text) |
| `source`, `source_id` | origin dataset and the document id in it |
| `language` | main language of the text |
| `words` | length in words |
| `mvp_flags` | red flag types annotated in the source, `;`-separated |
| `dirt` | kinds of noise in the text, `;`-separated (see below) |
| `license` | license of the text |
| `golden` | whether the text is part of the golden set |

## Dirt tags

| Tag | Meaning | How it is set |
|---|---|---|
| `ocr` | text went through OCR | by construction |
| `mixed_lang` | fragments in another language | automatic: at least 3 distinct words with non-ASCII letters, or any Cyrillic, Arabic or CJK character |
| `broken_layout` | sentences split across lines | automatic: at least 5% of lines end without punctuation and the next line starts in lowercase |
| `template_blanks` | unfilled fields | automatic: `___` or `[ ]` |
| `encoding` | broken characters | automatic: `�`, UTF-8 read as Latin-1 (`Ã©`, `â€™`), or lone Wingdings checkbox glyphs (`þ`, `ü`) |
| `translated` | non-native English of a translation | manual |
| `missing_fields` | schema fields absent from the lease | from the golden set |

Automatic tags can be corrected in `texts/dirt_manual.csv` (columns `id`, `add`, `remove`).

## Rebuilding

Download ALeaseBERT into `data/raw/aleasebert/` (see the main [README](../README.md)), then:

```sh
uv run python scripts/build_dataset.py
```

The selection is deterministic, so the output is the same on every run.
