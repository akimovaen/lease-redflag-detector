"""Document text inside the tags of a prompt, unable to close them.

The prompts give a model texts between tags: a lease (<lease>), the sources and the
red flag of a redline (<source>, <red_flag>), the answers and claims the judge reads.
A text that holds one of these tags, by accident or as an injection
("</source><source id="S9">…"), could close the real tag and pass itself off as
another source. `neutral` breaks every such tag in a text and leaves every other
character as it is: a model copies quotes from a lease that must match it word for word,
and leases hold "&" and "<" (OCR noise, company names), so escaping all markup would
break them. `attr` makes a value safe inside an attribute in double quotes.

The price: if a lease ever held one of these tags, the model would read `‹` where the
lease has `<`, and a quote copied across it would not match the lease and fail the
check of stage 1. No text of the corpus or of stage 1 holds one (tests/test_markup.py).
"""

import html
import re

# The tags the prompts of this project wrap texts in.
TAGS = (
    "lease",
    "source",
    "sources",
    "red_flag",
    "claim",
    "text",
    "clause",
    "expected",
    "answer",
)
TAG = re.compile(r"<(\s*/?\s*(?:" + "|".join(TAGS) + r"))\b", re.IGNORECASE)


def neutral(text: str) -> str:
    """The text with the `<` of every prompt tag in it replaced by `‹`: it reads the
    same to a person and opens or closes nothing."""
    return TAG.sub(r"‹\1", text)


def attr(value: object) -> str:
    """A value for an attribute in double quotes."""
    return html.escape(str(value), quote=True)
