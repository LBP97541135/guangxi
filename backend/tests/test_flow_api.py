import pytest

from app import repository as repo
from app.errors import ApiError
from app.schemas import AnswerIn, SessionStatus


def _answer_round(client, session_id, round_no, **answer_kwargs):
    payload = {"round": round_no, "answer": answer_kwargs}
    return client.post(f"/api/sessions/{session_id}/answers", json=payload)


def test_three_rounds_full_flow(client, db_factory):
    session_id = client.post("/api/sessions").json()["sessionId"]

    r1 = _answer_round(client, session_id, 1, type="option", optionKey="alone")
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["status"] == "QUESTION_2"
    assert body1["currentRound"] == 2
    assert body1["question"]["key"] == "desire_layer"

    r2 = _answer_round(client, session_id, 2, type="option", optionKey="rest")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["status"] == "QUESTION_3"
    assert body2["question"]["key"] == "deep_crack"

    r3 = _answer_round(client, session_id, 3, type="text", content="明明很累，却还是先照顾别人的情绪。")
    assert r3.status_code == 200
    body3 = r3.json()
    assert body3["status"] == "COMPLETED"
    assert body3["quote"]["content"].startswith("其实，你")

    with db_factory() as db:
        answers = repo.list_answers(db, session_id)
        assert [a.round_no for a in answers] == [1, 2, 3]
        assert answers[0].option_key == "alone"
        assert answers[0].content is None
        assert answers[2].content == "明明很累，却还是先照顾别人的情绪。"

    follow_up = client.get(f"/api/sessions/{session_id}").json()
    assert follow_up["status"] == "COMPLETED"
    assert follow_up["quote"]["content"] == body3["quote"]["content"]


def test_fake_generation_called_exactly_once(client):
    session_id = client.post("/api/sessions").json()["sessionId"]
    _answer_round(client, session_id, 1, type="option", optionKey="alone")
    _answer_round(client, session_id, 2, type="option", optionKey="rest")

    _answer_round(client, session_id, 3, type="text", content="答案")

    assert client.app.state.generation_service.calls == 1


def test_round_mismatch_rejected(client):
    session_id = client.post("/api/sessions").json()["sessionId"]

    response = _answer_round(client, session_id, 2, type="text", content="跳轮回答")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ROUND_MISMATCH"


def test_option_from_other_question_rejected(client):
    session_id = client.post("/api/sessions").json()["sessionId"]

    response = _answer_round(client, session_id, 1, type="option", optionKey="rest")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ANSWER"


def test_duplicate_submit_returns_stable_error(client, db_factory):
    session_id = client.post("/api/sessions").json()["sessionId"]

    first = _answer_round(client, session_id, 1, type="option", optionKey="alone")
    second = _answer_round(client, session_id, 1, type="option", optionKey="alone")

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ANSWER_ALREADY_EXISTS"
    with db_factory() as db:
        assert len(repo.list_answers(db, session_id)) == 1


def test_concurrent_same_round_only_one_wins(client, db_factory):
    session_id = client.post("/api/sessions").json()["sessionId"]
    flow = client.app.state.flow_service
    questions = client.app.state.questions

    session_a = db_factory()
    session_b = db_factory()
    try:
        result_a = flow.submit_answer(
            session_a, session_id, 1, AnswerIn(type="option", option_key="alone")
        )
        session_a.commit()

        with pytest.raises(ApiError) as exc_info:
            flow.submit_answer(
                session_b, session_id, 1, AnswerIn(type="option", option_key="conflict")
            )
            session_b.commit()
        assert exc_info.value.code == "ANSWER_ALREADY_EXISTS"
    finally:
        session_a.close()
        session_b.close()

    with db_factory() as db:
        assert len(repo.list_answers(db, session_id)) == 1
        row = repo.get_session(db, session_id)
        assert row.status == SessionStatus.QUESTION_2.value


def test_closed_states_reject_answers(client, db_factory):
    for status in (SessionStatus.GENERATING, SessionStatus.COMPLETED, SessionStatus.FAILED):
        session_id = client.post("/api/sessions").json()["sessionId"]
        with db_factory() as db:
            row = repo.get_session(db, session_id)
            repo.update_session_state(db, row, status=status.value, current_round=3)
            db.commit()

        response = _answer_round(client, session_id, 3, type="text", content="答案")

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "INVALID_SESSION_STATE"


def test_text_answer_too_long_rejected(client):
    session_id = client.post("/api/sessions").json()["sessionId"]

    response = _answer_round(client, session_id, 1, type="text", content="长" * 501)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ANSWER_TOO_LONG"


def test_answers_for_missing_session_404(client):
    response = _answer_round(
        client, "00000000-0000-0000-0000-000000000000", 1, type="text", content="答案"
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_cannot_skip_round_then_continue(client):
    session_id = client.post("/api/sessions").json()["sessionId"]
    _answer_round(client, session_id, 1, type="option", optionKey="alone")

    wrong = _answer_round(client, session_id, 1, type="option", optionKey="conflict")
    right = _answer_round(client, session_id, 2, type="option", optionKey="rest")

    assert wrong.status_code == 409
    assert right.status_code == 200
    assert right.json()["status"] == "QUESTION_3"
