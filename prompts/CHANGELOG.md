# Prompt changelog

Prompts live in `prompts/<task>/<version>.md` and are sent as the system prompt.
Field-level instructions are in the field descriptions of the output schema
(`src/lease_redflag_detector/extraction/schema.py`), which is sent with every request.
Every result in `results/` records the prompt version that produced it.

## extraction

### v1 — baseline

Role, a note that the text may be OCR'd, translated or mixed-language, and the
labeling rules of the golden set in short: null for absent values, ISO dates, computed
end date, rent per period without VAT, `indexation: none` when the rent never changes,
and verbatim quotes for red flags.
