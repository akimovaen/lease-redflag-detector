# Data

Lease texts used to evaluate extraction, and the golden set they are scored against.

## Layout

```
data/
  texts/
    manifest.csv      # one row per text: source, language, length, dirt tags, license
    dirt_manual.csv   # manual corrections to the dirt tags
    *.txt             # the texts, one paragraph per line
  golden/             # hand-labeled reference outputs
  processed/
    golden_hints/     # ALeaseBERT annotations to help labeling
  raw/                # original downloads, not committed
```

## Sources

### ALeaseBERT (groups A and B)

Texts with the `alb_` (group A) and `ocr_` (group B) prefixes come from:

> Leivaditi, S., Rossi, J., Kanoulas, E. *ALeaseBERT: A Benchmark for Lease Contract Review.*
> University of Amsterdam. https://doi.org/10.21942/uva.19732993

Licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).
They may be used for non-commercial purposes only, with attribution.
The [MIT License](../LICENSE) of this repository does **not** apply to them.

Changes made:

- **Group A (15 leases):** converted from the dataset's annotated HTML to plain text with
  one paragraph per line. The wording is unchanged. Line N of a text corresponds to
  paragraph `s1pN` in the original annotations.
- **Group B (5 other leases):** rendered as printed pages, degraded like an office scan
  (skew, blur, specks, low contrast, JPEG artifacts) and read back with Tesseract OCR.
  The text contains real OCR errors and follows the physical lines of the page, so it
  no longer aligns with the original paragraphs. Noise level per text is in the
  `ocr_noise` column:

  | Level | Word error rate vs. the original |
  |---|---|
  | `light` | about 3% |
  | `medium` | about 5–7% |
  | `heavy` | about 15% |

Selection: leases of at most 10,000 words that contain at least 3 of the 5 red flag types
used in this project (`break_option`, `services_charges`, `sublease_permitted`,
`reinstatement_clause`, `landlord_repairs`), sampled with a fixed seed across three
length buckets (under 2,000 / 2,000–5,000 / 5,000–10,000 words). Group B uses only the
two shorter buckets.

## Golden set

`golden/<id>.json` holds the reference output for a text, in the `LeaseAbstract` schema
(`src/lease_redflag_detector/extraction/schema.py`). Texts with a golden file are marked
`golden = yes` in the manifest.

**Provenance:** values were drafted by Claude (Opus 5.5) from the full texts, with quotes cut
verbatim from the text files by a one-off script, and then reviewed and corrected by a human.
Because the reference was drafted by a Claude model, scores of Claude models against it may
be biased upward; keep this in mind when comparing them with other models.

Labeling rules:

- **Values are the true values**, not their OCR spelling: if OCR turned `June` into `Jane`,
  the golden date still uses June. The model is scored on recovering what the lease says.
- **But only what the text still contains.** If OCR dropped or garbled a passage beyond
  recognition, information found only there is treated as absent (`null`, no red flag):
  the model cannot recover it.
- **Quotes are verbatim from `texts/<id>.txt`**, including OCR errors, because that is the
  text the model sees. Differences in whitespace and line breaks are ignored.
- **`null` means the lease does not state it.** A correct `null` counts as a correct answer.
- Dates as `YYYY-MM-DD`; `end_date` computed from the start date and term if not stated.
- `rent`: base rent for one period without VAT, currency as an ISO 4217 code.
- `area`: total leased area in the unit the lease uses.
- `indexation`: `none` when the lease has no clause changing the rent during the term.
- One red flag entry per clause; only clauses risky for the landlord under the definitions
  in the schema.
- The landlord's duty to remedy defects found when the premises are handed over is not
  `landlord_repairs`: it is a one-off duty to deliver the premises in good condition, not
  a burden of repairs during the term.

Tools:

```sh
uv run python scripts/make_golden_drafts.py   # blank golden files + hints, never overwrites
uv run python scripts/check_golden.py         # schema and verbatim-quote check
```

Hints in `processed/golden_hints/<id>.md` list the spans the ALeaseBERT authors annotated
for each lease, with line numbers. They are a starting point, not answers: most ALeaseBERT
red flag spans protect the landlord rather than put it at risk.

## Manifest

| Column | Meaning |
|---|---|
| `id` | file name without `.txt` |
| `group` | how the text was produced (A: ALeaseBERT plain text, B: ALeaseBERT scan + OCR) |
| `source`, `source_id` | origin dataset and the document id in it |
| `language` | main language of the text |
| `words` | length in words |
| `mvp_flags` | red flag types annotated in the source, `;`-separated |
| `dirt` | kinds of noise in the text, `;`-separated (see below) |
| `ocr_noise` | scan noise level for group B (`light`, `medium`, `heavy`) |
| `license` | license of the text |
| `golden` | whether the text is part of the golden set |

## Dirt tags

| Tag | Meaning | How it is set |
|---|---|---|
| `ocr` | text went through OCR | by construction |
| `mixed_lang` | fragments in another language | automatic: at least 3 distinct words with non-ASCII letters, or any Cyrillic, Arabic or CJK character. For OCR texts it is checked on the original, since misreads like `éach` look foreign |
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

Group B also needs [Tesseract](https://github.com/tesseract-ocr/tesseract)
(`brew install tesseract`). Scans and OCR output are cached in `data/raw/scans/`;
delete that folder to rebuild them after changing the noise settings in `scripts/scan.py`.

The selection and the scan noise are seeded, so the output is the same on every run.
