from types import SimpleNamespace

import pytest

from lease_redflag_detector.extraction.extractor import RunConfig
from lease_redflag_detector.rag.judge import FaithfulnessJudgment, Judge, JudgeError

CONFIG = RunConfig(name="judge", provider="anthropic", model="m", prompt="p")


def judge_returning(text: str, stop_reason: str = "end_turn") -> Judge:
    judge = Judge(CONFIG)
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    judge.client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: response)
    )
    return judge


@pytest.fixture(autouse=True)
def no_prompt_files(monkeypatch):
    monkeypatch.setattr("lease_redflag_detector.rag.judge.load_prompt", lambda p: p)


def test_a_valid_judgment_is_parsed():
    judge = judge_returning('{"claims": []}')
    assert judge.ask("p", "c", FaithfulnessJudgment) == FaithfulnessJudgment(claims=[])
    assert judge.usage == {"input_tokens": 10, "output_tokens": 5}


def test_a_cut_off_or_malformed_judgment_is_a_judge_error():
    with pytest.raises(JudgeError, match="cut off"):
        judge_returning('{"claims": [', "max_tokens").ask(
            "p", "c", FaithfulnessJudgment
        )
    with pytest.raises(JudgeError):
        judge_returning('{"claims": 1}').ask("p", "c", FaithfulnessJudgment)
