"""Human confirmation of an action with a side effect.

The tool itself asks before it acts, so no text of the model or of a document can
stand in for the lawyer's answer: the check is in the code, not in the prompt.

- `TerminalConfirmer`: the lawyer answers in the terminal. Without a terminal (a
  background run, piped input) the answer is no.
- `ScriptedConfirmer`: the answers an eval task sets in advance; it records what it
  was asked.
"""

import sys
from typing import Protocol

YES = {"так", "т", "yes", "y"}
NO = {"ні", "н", "no", "n"}


class Confirmer(Protocol):
    def __call__(self, question: str) -> bool: ...


class TerminalConfirmer:
    def __call__(self, question: str) -> bool:
        print(f"\n──────── Потрібне ваше підтвердження ────────\n{question}")
        if not sys.stdin.isatty():
            print("Немає термінала для відповіді: дію не виконано.")
            return False
        while True:
            try:
                answer = input("[так/ні]: ").strip().casefold()
            except EOFError:
                return False
            if answer in YES or answer in NO:
                return answer in YES
            print("Відповідайте «так» або «ні».")


class ScriptedConfirmer:
    def __init__(self, *answers: bool):
        self.answers = list(answers)
        self.asked: list[str] = []

    def __call__(self, question: str) -> bool:
        self.asked.append(question)
        return self.answers.pop(0) if self.answers else False


def deny(question: str) -> bool:
    return False
