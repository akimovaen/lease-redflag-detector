"""BM25 over lemmas of Ukrainian words.

Ukrainian inflects nouns, adjectives and verbs: "орендодавець", "орендодавця",
"орендодавцеві" are one word to a lawyer and three to plain BM25. Every word is
reduced to its dictionary form with pymorphy3 before indexing and searching, and the
most frequent function words are dropped. Numbers are kept: a query for "статті 776"
must match "Стаття 776".

The Ukrainian dictionary of pymorphy3 has no frequencies, so its first parse is
arbitrary ("пені" → "пен", "плати" → "плат"). Of the possible lemmas of a word, the
one most frequent in the indexed corpus is taken: "пеня" occurs in every case form,
"пен" in none.

The Civil Code speaks of "найм" where leases and lawyers say "оренда" (art. 759 puts
them as one: "договір найму (оренди)"), so its terms are mapped to the usual ones.
"""

import re
from collections import Counter
from collections.abc import Iterable
from functools import cache

import bm25s
import numpy as np

TOKEN = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
CYRILLIC = re.compile(r"[а-яіїєґ]")
FUNCTION_WORDS = """
    а або аж б би бо був бути в вже від для до є же з за зі і із й його її їх
    к коли ли на над не ні о об однак от по при про проте під себто та так також те
    то тобто той у хоча це цей ця чи що щоб як який якщо
    """
STOPWORDS = frozenset(FUNCTION_WORDS.split())
SYNONYMS = {
    "найм": "оренда",
    "наймодавець": "орендодавець",
    "наймач": "орендар",
    "піднайм": "суборенда",
}


@cache
def morph():
    import pymorphy3

    return pymorphy3.MorphAnalyzer(lang="uk")


@cache
def candidates(word: str) -> tuple[str, ...]:
    """Possible lemmas of a casefolded word, in the dictionary's order."""
    if word.isdigit() or not CYRILLIC.search(word):
        return (word,)
    return tuple(dict.fromkeys(parse.normal_form for parse in morph().parse(word)))


def words(text: str) -> list[str]:
    found = (m.group(0).casefold().replace("’", "'") for m in TOKEN.finditer(text))
    return [word for word in found if word not in STOPWORDS]


class Lemmatizer:
    """Chooses among the lemmas of a word by their frequency in a corpus."""

    def __init__(self, texts: Iterable[str] = ()):
        self.counts: Counter[str] = Counter()
        for text in texts:
            for word in words(text):
                self.counts.update(candidates(word))
        self._lemmas: dict[str, str] = {}

    def lemma(self, word: str) -> str:
        if word not in self._lemmas:
            options = candidates(word)
            best = max(options, key=lambda c: (self.counts[c], -options.index(c)))
            self._lemmas[word] = SYNONYMS.get(best, best)
        return self._lemmas[word]

    def tokenize(self, text: str) -> list[str]:
        lemmas = (self.lemma(word) for word in words(text))
        return [lemma for lemma in lemmas if lemma not in STOPWORDS]


class BM25:
    def __init__(self, texts: list[str]):
        self.lemmatizer = Lemmatizer(texts)
        self.index = bm25s.BM25()
        self.index.index(
            [self.lemmatizer.tokenize(text) for text in texts], show_progress=False
        )

    def scores(self, query: str) -> np.ndarray:
        """A score for every indexed text, in index order."""
        return np.asarray(self.index.get_scores(self.lemmatizer.tokenize(query)))
