import json

import pytest

from app.questions import QuestionsConfig, load_questions


def _write(tmp_path, payload) -> str:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _valid_payload() -> dict:
    return {
        "questions": [
            {
                "round": 1,
                "key": "q1",
                "text": "第一问？",
                "options": [{"key": "a", "label": "甲"}, {"key": "b", "label": "乙"}],
                "allowFreeText": True,
            },
            {
                "round": 2,
                "key": "q2",
                "text": "第二问？",
                "options": [{"key": "c", "label": "丙"}],
                "allowFreeText": False,
            },
            {
                "round": 3,
                "key": "q3",
                "text": "第三问？",
                "options": [],
                "allowFreeText": True,
            },
        ]
    }


def test_placeholder_config_loads():
    config = load_questions(__import__("pathlib").Path("config/questions.json"))

    assert [q.round for q in config.questions] == [1, 2, 3]
    assert all(q.text for q in config.questions)
    assert config.by_round(1).key == "surface_scene"


def test_valid_config_loads_as_typed_objects(tmp_path):
    config = load_questions(_write(tmp_path, _valid_payload()))

    assert len(config.questions) == 3
    assert config.by_round(2).options[0].label == "丙"


def test_missing_round_2_fails(tmp_path):
    payload = _valid_payload()
    del payload["questions"][1]

    with pytest.raises(Exception, match="1、2、3"):
        load_questions(_write(tmp_path, payload))


def test_duplicate_question_key_fails(tmp_path):
    payload = _valid_payload()
    payload["questions"][1]["key"] = "q1"

    with pytest.raises(Exception, match="问题 Key 重复"):
        load_questions(_write(tmp_path, payload))


def test_duplicate_option_key_fails(tmp_path):
    payload = _valid_payload()
    payload["questions"][0]["options"][1]["key"] = "a"

    with pytest.raises(Exception, match="选项 Key 重复"):
        load_questions(_write(tmp_path, payload))


def test_unanswerable_question_fails(tmp_path):
    payload = _valid_payload()
    payload["questions"][2]["allowFreeText"] = False

    with pytest.raises(Exception, match="allowFreeText"):
        load_questions(_write(tmp_path, payload))


def test_invalid_json_fails(tmp_path):
    path = tmp_path / "questions.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(Exception, match="合法 JSON"):
        load_questions(path)


def test_by_round_missing_raises_key_error():
    config = QuestionsConfig.model_validate(_valid_payload())

    with pytest.raises(KeyError):
        config.by_round(9)
