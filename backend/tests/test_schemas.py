import pytest
from pydantic import ValidationError

from app.schemas import (
    AnswerIn,
    SessionOut,
    SessionStatus,
    SubmitAnswerRequest,
)


def _answer(**kwargs) -> dict:
    return {"type": "text", "content": "明明很累，却还是习惯先照顾别人的情绪。", **kwargs}


def test_round_out_of_range_fails():
    for bad_round in (0, 4):
        with pytest.raises(ValidationError):
            SubmitAnswerRequest.model_validate({"round": bad_round, "answer": _answer()})


def test_rounds_1_to_3_valid():
    for round_no in (1, 2, 3):
        request = SubmitAnswerRequest.model_validate({"round": round_no, "answer": _answer()})
        assert request.round == round_no


def test_text_answer_empty_fails():
    with pytest.raises(ValidationError):
        AnswerIn.model_validate({"type": "text", "content": "   "})


def test_text_answer_missing_content_fails():
    with pytest.raises(ValidationError):
        AnswerIn.model_validate({"type": "text"})


def test_option_answer_requires_option_key():
    with pytest.raises(ValidationError):
        AnswerIn.model_validate({"type": "option"})


def test_option_answer_with_content_fails():
    with pytest.raises(ValidationError):
        AnswerIn.model_validate({"type": "option", "optionKey": "alone", "content": "x"})


def test_text_answer_with_option_key_fails():
    with pytest.raises(ValidationError):
        AnswerIn.model_validate({"type": "text", "content": "x", "optionKey": "alone"})


def test_valid_option_answer():
    answer = AnswerIn.model_validate({"type": "option", "optionKey": "alone"})
    assert answer.option_key == "alone"


def test_session_out_serializes_camel_case():
    out = SessionOut(
        session_id="abc",
        status=SessionStatus.QUESTION_1,
        current_round=1,
        question={"key": "k", "text": "t", "options": [{"key": "alone", "label": "一个人"}], "allow_free_text": True},
    )
    data = out.model_dump(by_alias=True)

    assert data["sessionId"] == "abc"
    assert data["currentRound"] == 1
    assert data["question"]["allowFreeText"] is True
