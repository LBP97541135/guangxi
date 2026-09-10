from app import repository as repo
from app.models import QuoteStatus
from app.schemas import SessionStatus


def test_create_session_returns_first_question(client):
    response = client.post("/api/sessions")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "QUESTION_1"
    assert body["currentRound"] == 1
    question = body["question"]
    assert question["key"] == "surface_scene"
    assert question["text"]
    assert len(question["options"]) >= 1
    assert question["allowFreeText"] is True
    assert len(body["sessionId"]) == 36


def test_create_two_sessions_different_ids(client):
    first = client.post("/api/sessions").json()
    second = client.post("/api/sessions").json()

    assert first["sessionId"] != second["sessionId"]


def test_get_new_session_returns_first_question(client):
    created = client.post("/api/sessions").json()

    response = client.get(f"/api/sessions/{created['sessionId']}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "QUESTION_1"
    assert body["question"]["key"] == "surface_scene"


def test_get_missing_session_returns_404_with_code(client):
    response = client.get("/api/sessions/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "SESSION_NOT_FOUND"
    assert error["retryable"] is False


def test_get_does_not_modify_state(client, db_factory):
    created = client.post("/api/sessions").json()

    first = client.get(f"/api/sessions/{created['sessionId']}").json()
    second = client.get(f"/api/sessions/{created['sessionId']}").json()

    assert first == second
    with db_factory() as db:
        assert repo.list_answers(db, created["sessionId"]) == []
        assert repo.get_quote(db, created["sessionId"]) is None


def test_get_returns_question_per_round_state(client, db_factory):
    session_id = client.post("/api/sessions").json()["sessionId"]

    with db_factory() as db:
        row = repo.get_session(db, session_id)
        repo.update_session_state(db, row, status=SessionStatus.QUESTION_2.value, current_round=2)
        db.commit()

    response = client.get(f"/api/sessions/{session_id}")

    body = response.json()
    assert body["status"] == "QUESTION_2"
    assert body["currentRound"] == 2
    assert body["question"]["key"] == "desire_layer"


def test_get_generating_returns_status_only(client, db_factory):
    session_id = client.post("/api/sessions").json()["sessionId"]

    with db_factory() as db:
        row = repo.get_session(db, session_id)
        repo.update_session_state(db, row, status=SessionStatus.GENERATING.value, current_round=3)
        repo.ensure_quote(db, session_id, model="fake")
        db.commit()

    response = client.get(f"/api/sessions/{session_id}")

    body = response.json()
    assert body["status"] == "GENERATING"
    assert body["question"] is None
    assert body["quote"] is None


def test_get_failed_returns_retryable_state(client, db_factory):
    session_id = client.post("/api/sessions").json()["sessionId"]

    with db_factory() as db:
        row = repo.get_session(db, session_id)
        repo.update_session_state(db, row, status=SessionStatus.FAILED.value, current_round=3)
        db.commit()

    response = client.get(f"/api/sessions/{session_id}")

    body = response.json()
    assert body["status"] == "FAILED"
    assert body["quote"] is None


def test_get_completed_returns_unique_quote(client, db_factory):
    session_id = client.post("/api/sessions").json()["sessionId"]

    with db_factory() as db:
        row = repo.get_session(db, session_id)
        repo.update_session_state(db, row, status=SessionStatus.COMPLETED.value, current_round=3)
        quote = repo.ensure_quote(db, session_id, model="fake")
        repo.mark_quote_succeeded(db, quote, "其实，你不是习惯沉默。", model="fake")
        db.commit()

    response = client.get(f"/api/sessions/{session_id}")

    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["quote"]["content"] == "其实，你不是习惯沉默。"
    assert body["question"] is None


def test_openapi_contains_contract_paths(client):
    schema = client.get("/openapi.json").json()

    paths = schema["paths"]
    assert "/api/sessions" in paths
    assert "/api/sessions/{session_id}" in paths
    assert "/api/health" in paths
