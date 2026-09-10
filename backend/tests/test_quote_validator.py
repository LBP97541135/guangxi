from app.llm.validator import QuoteValidator


def test_valid_quote_passes():
    validator = QuoteValidator()

    ok, reason = validator.validate("其实，你只是还没和自己好好和解。")

    assert ok is True
    assert reason == ""


def test_valid_quote_with_ellipsis_passes():
    assert QuoteValidator().validate("其实，你……一直都在撑着。")[0] is True


def test_empty_results_rejected():
    validator = QuoteValidator()
    for bad in (None, "", "   "):
        ok, reason = validator.validate(bad)
        assert ok is False
        assert reason == "empty"


def test_wrong_prefix_rejected():
    validator = QuoteValidator()
    for bad in ("你就是很好的人。", "其实你很好。", "其实， 你很好。"):
        ok, reason = validator.validate(bad)
        assert ok is False
        assert reason == "prefix"


def test_length_boundary():
    validator = QuoteValidator(max_chars=50)

    fifty = "其实，你" + "字" * 46
    assert len(fifty) == 50
    assert validator.validate(fifty)[0] is True

    fifty_one = fifty + "字"
    ok, reason = validator.validate(fifty_one)
    assert ok is False
    assert reason.startswith("too_long")


def test_mbti_tokens_rejected():
    validator = QuoteValidator()
    ok, reason = validator.validate("其实，你像 INFJ 一样安静。")
    assert ok is False
    assert reason == "forbidden:INFJ"

    ok, reason = validator.validate("其实，你有自己的 MBTI。")
    assert ok is False
    assert reason == "forbidden:MBTI"


def test_personality_label_words_rejected():
    validator = QuoteValidator()
    for bad in ("其实，你是典型的天蝎座。", "其实，你像九型人格里的那种人。", "其实，你是十足的 I人。"):
        ok, reason = validator.validate(bad)
        assert ok is False
        assert reason.startswith("forbidden")


def test_classification_expressions_rejected():
    validator = QuoteValidator()
    for bad in ("其实，你属于敏感的人。", "其实，你是思考型的人。", "其实，你是那类人。"):
        ok, reason = validator.validate(bad)
        assert ok is False
        assert reason.startswith("classification")
