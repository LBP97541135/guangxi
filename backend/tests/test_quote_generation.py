import pytest

from app import repository as repo
from app.llm.fake import FAKE_QUOTE
from app.llm.provider import GenerationCandidate, ModelCallError
from app.schemas import SessionStatus

GOOD_QUOTE = "其实，你值得被自己温柔对待。"
BAD_QUOTE = "你是INTJ型的人，天生如此。"


class StubProvider:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _complete_three_rounds(client):
    session_id = client.post("/api/sessions").json()["sessionId"]
    client.post(f"/api/sessions/{session_id}/answers", json={"round": 1, "answer": {"type": "option", "optionKey": "alone"}})
    client.post(f"/api/sessions/{session_id}/answers", json={"round": 2, "answer": {"type": "option", "optionKey": "rest"}})
    return session_id


def _submit_round3(client, session_id):
    return client.post(
        f"/api/sessions/{session_id}/answers",
        json={"round": 3, "answer": {"type": "text", "content": "深夜总是想太多。"}},
    )


def test_fake_provider_full_flow_returns_compliant_quote(client):
    session_id = _complete_three_rounds(client)

    response = _submit_round3(client, session_id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["quote"]["content"] == FAKE_QUOTE


def test_first_invalid_second_valid_saves_second_only(client):
    session_id = _complete_three_rounds(client)
    coordinator = client.app.state.generation_service
    coordinator.provider = StubProvider(
        [
            GenerationCandidate(text=BAD_QUOTE, model="stub"),
            GenerationCandidate(text=GOOD_QUOTE, model="stub"),
        ]
    )

    response = _submit_round3(client, session_id)

    assert response.status_code == 200
    assert response.json()["quote"]["content"] == GOOD_QUOTE
    assert coordinator.calls == 2
    with client.app.state.session_factory() as db:
        quote = repo.get_quote(db, session_id)
        assert quote.content == GOOD_QUOTE
        assert quote.generation_attempts == 2
        assert quote.status == "SUCCEEDED"


def test_both_invalid_marks_failed_and_keeps_answers(client):
    session_id = _complete_three_rounds(client)
    coordinator = client.app.state.generation_service
    coordinator.provider = StubProvider(
        [
            GenerationCandidate(text=BAD_QUOTE, model="stub"),
            GenerationCandidate(text=BAD_QUOTE, model="stub"),
        ]
    )

    response = _submit_round3(client, session_id)

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "GENERATION_FAILED"
    assert error["retryable"] is True
    assert coordinator.calls == 2

    with client.app.state.session_factory() as db:
        row = repo.get_session(db, session_id)
        assert row.status == SessionStatus.FAILED.value
        assert len(repo.list_answers(db, session_id)) == 3
        quote = repo.get_quote(db, session_id)
        assert quote.status == "FAILED"
        assert quote.content is None


def test_double_timeout_retries_once_then_fails(client):
    session_id = _complete_three_rounds(client)
    coordinator = client.app.state.generation_service
    timeout = ModelCallError("MODEL_TIMEOUT", "模型调用超时")
    coordinator.provider = StubProvider([timeout, timeout])

    response = _submit_round3(client, session_id)

    assert response.status_code == 502
    assert coordinator.calls == 2
    with client.app.state.session_factory() as db:
        assert repo.get_session(db, session_id).status == SessionStatus.FAILED.value


def test_manual_retry_after_failure_succeeds(client):
    session_id = _complete_three_rounds(client)
    coordinator = client.app.state.generation_service
    bad = GenerationCandidate(text=BAD_QUOTE, model="stub")
    coordinator.provider = StubProvider([bad, bad])
    assert _submit_round3(client, session_id).status_code == 502

    coordinator.provider = StubProvider([GenerationCandidate(text=GOOD_QUOTE, model="stub")])
    response = client.post(f"/api/sessions/{session_id}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["quote"]["content"] == GOOD_QUOTE
    with client.app.state.session_factory() as db:
        assert repo.get_session(db, session_id).status == SessionStatus.COMPLETED.value


def test_manual_retry_still_failed_keeps_retryable(client):
    session_id = _complete_three_rounds(client)
    coordinator = client.app.state.generation_service
    bad = GenerationCandidate(text=BAD_QUOTE, model="stub")
    coordinator.provider = StubProvider([bad, bad])
    _submit_round3(client, session_id)

    coordinator.provider = StubProvider([bad, bad])
    response = client.post(f"/api/sessions/{session_id}/retry")

    assert response.status_code == 502
    assert response.json()["error"]["retryable"] is True
    with client.app.state.session_factory() as db:
        assert repo.get_session(db, session_id).status == SessionStatus.FAILED.value
        assert len(repo.list_answers(db, session_id)) == 3
        assert repo.get_quote(db, session_id).generation_attempts == 4


def test_retry_on_completed_conflicts_and_creates_no_quote(client):
    session_id = _complete_three_rounds(client)
    _submit_round3(client, session_id)
    coordinator = client.app.state.generation_service
    calls_before = coordinator.calls

    response = client.post(f"/api/sessions/{session_id}/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_SESSION_STATE"
    assert coordinator.calls == calls_before
    with client.app.state.session_factory() as db:
        assert len(db.query(repo.Quote).filter(repo.Quote.session_id == session_id).all()) == 1


def test_retry_on_open_session_conflicts(client):
    session_id = client.post("/api/sessions").json()["sessionId"]

    response = client.post(f"/api/sessions/{session_id}/retry")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_SESSION_STATE"


def test_incomplete_answers_never_call_provider(client, db_factory):
    session_id = client.post("/api/sessions").json()["sessionId"]
    coordinator = client.app.state.generation_service
    coordinator.provider = StubProvider([GenerationCandidate(text=GOOD_QUOTE, model="stub")])
    with db_factory() as db:
        row = repo.get_session(db, session_id)
        repo.update_session_state(db, row, status=SessionStatus.GENERATING.value, current_round=3)
        repo.add_answer(db, session_id, 1, "text", None, "只有一条答案")
        db.commit()

    from app.services.generation import QuoteGenerationError

    with db_factory() as db:
        row = repo.get_session(db, session_id)
        with pytest.raises(RuntimeError, match="答案不完整"):
            coordinator.run(db, row)

    assert coordinator.provider.calls == 0


def test_completed_session_query_returns_original_quote(client):
    session_id = _complete_three_rounds(client)
    original = _submit_round3(client, session_id).json()["quote"]

    again = client.get(f"/api/sessions/{session_id}").json()

    assert again["quote"]["id"] == original["id"]
    assert again["quote"]["content"] == original["content"]
