import json
from pathlib import Path

import pytest

from app.questions import QuestionsConfig, load_questions


def _write(tmp_path, payload) -> Path:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _question(round_no: int, key: str, **extra) -> dict:
    payload = {
        "round": round_no,
        "key": key,
        "text": f"第{round_no}问：{key}？",
        "options": [{"key": "c1", "label": "甲"}, {"key": "c2", "label": "乙"}],
        "allowFreeText": True,
    }
    payload.update(extra)
    return payload


def _valid_payload() -> dict:
    return {
        "questions": [
            _question(1, "q1", title="题一", sceneExample="示例画面一"),
            _question(2, "q2"),
            _question(3, "q3"),
        ]
    }


def test_placeholder_config_loads_full_bank():
    config = load_questions(Path("config/questions.json"))

    assert {q.round for q in config.questions} == {1, 2, 3}
    assert len(config.questions) == 150
    for round_no in (1, 2, 3):
        variants = config.variants_for_round(round_no)
        assert len(variants) == 50
        for variant in variants:
            assert variant.title
            assert variant.scene_example
            assert variant.allow_free_text is True
            assert len(variant.options) == 4
    assert config.default_for_round(1).key == "act1_01"


def test_valid_config_loads_as_typed_objects(tmp_path):
    config = load_questions(_write(tmp_path, _valid_payload()))

    assert len(config.questions) == 3
    second = config.by_key("q2")
    assert second.options[0].label == "甲"
    assert config.by_key("q1").title == "题一"
    assert config.by_key("q1").scene_example == "示例画面一"


def test_multiple_variants_per_round_valid(tmp_path):
    payload = _valid_payload()
    payload["questions"].append(_question(1, "q1b", title="备选"))

    config = load_questions(_write(tmp_path, payload))

    assert len(config.variants_for_round(1)) == 2
    assert config.default_for_round(1).key == "q1"


def test_missing_round_2_fails(tmp_path):
    payload = _valid_payload()
    payload["questions"] = [q for q in payload["questions"] if q["round"] != 2]

    with pytest.raises(Exception, match="1、2、3"):
        load_questions(_write(tmp_path, payload))


def test_duplicate_question_key_fails(tmp_path):
    payload = _valid_payload()
    payload["questions"][1]["key"] = "q1"

    with pytest.raises(Exception, match="问题 Key 重复"):
        load_questions(_write(tmp_path, payload))


def test_duplicate_option_key_fails(tmp_path):
    payload = _valid_payload()
    payload["questions"][0]["options"][1]["key"] = "c1"

    with pytest.raises(Exception, match="选项 Key 重复"):
        load_questions(_write(tmp_path, payload))


def test_unanswerable_question_fails(tmp_path):
    payload = _valid_payload()
    payload["questions"][2]["options"] = []
    payload["questions"][2]["allowFreeText"] = False

    with pytest.raises(Exception, match="allowFreeText"):
        load_questions(_write(tmp_path, payload))


def test_invalid_json_fails(tmp_path):
    path = tmp_path / "questions.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(Exception, match="合法 JSON"):
        load_questions(path)


def test_missing_round_or_key_raises_key_error():
    config = QuestionsConfig.model_validate(_valid_payload())

    with pytest.raises(KeyError):
        config.variants_for_round(9)
    with pytest.raises(KeyError):
        config.by_key("nope")
