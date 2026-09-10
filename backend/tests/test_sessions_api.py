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
    assert question["key"] == "act1_01"
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
    assert body["question"]["key"] == "act1_01"


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
    assert body["question"]["key"] == "act2_01"


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
    assert "/api/sessions/{session_id}/questions/switch" in paths
    assert "/api/health" in paths


def test_switch_question_cycles_round_variants(client):
    session_id = client.post("/api/sessions").json()["sessionId"]

    first = client.get(f"/api/sessions/{session_id}").json()["question"]["key"]
    second = client.post(f"/api/sessions/{session_id}/questions/switch").json()["question"]["key"]
    third = client.post(f"/api/sessions/{session_id}/questions/switch").json()["question"]["key"]
    assert (first, second, third) == ("act1_01", "act1_02", "act1_03")

    for _ in range(47):
        client.post(f"/api/sessions/{session_id}/questions/switch")
    wrapped = client.post(f"/api/sessions/{session_id}/questions/switch").json()["question"]["key"]
    assert wrapped == first


def test_switch_question_returns_title_and_scene_example(client):
    session_id = client.post("/api/sessions").json()["sessionId"]

    question = client.post(f"/api/sessions/{session_id}/questions/switch").json()["question"]

    assert question["title"]
    assert question["sceneExample"]
    assert question["allowFreeText"] is True


def test_switch_question_rejected_when_closed(client, db_factory):
    session_id = client.post("/api/sessions").json()["sessionId"]
    with db_factory() as db:
        row = repo.get_session(db, session_id)
        repo.update_session_state(db, row, status=SessionStatus.COMPLETED.value, current_round=3)
        db.commit()

    response = client.post(f"/api/sessions/{session_id}/questions/switch")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_SESSION_STATE"


def test_switch_question_missing_session_404(client):
    response = client.post("/api/sessions/00000000-0000-0000-0000-000000000000/questions/switch")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"
