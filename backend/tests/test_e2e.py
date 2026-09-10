"""端到端验收：只通过 HTTP 接口走完整 Demo 链路（模型边界用 Stub 替换）。

覆盖 T08 定义的 E2E-01 至 E2E-05。
"""

import pytest

from app import repository as repo
from app.llm.provider import GenerationCandidate, ModelCallError

GOOD_QUOTE = "其实，你值得被自己温柔对待。"

INVALID_SAMPLES = {
    "empty": "",
    "wrong_prefix": "你就是很努力的人。",
    "too_long": "其实，你" + "很" * 60,
    "forbidden": "其实，你像典型的天蝎座。",
}


class StubProvider:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return GenerationCandidate(text=result, model="stub")


def _submit(client, session_id, round_no, answer):
    return client.post(f"/api/sessions/{session_id}/answers", json={"round": round_no, "answer": answer})


def _use_provider(client, *results):
    stub = StubProvider(list(results))
    client.app.state.generation_service.provider = stub
    return stub


# E2E-01 正常路径
def test_e2e_01_normal_path(client):
    created = client.post("/api/sessions")
    assert created.status_code == 201
    session_id = created.json()["sessionId"]
    assert created.json()["question"]["key"] == "surface_scene"

    r1 = _submit(client, session_id, 1, {"type": "option", "optionKey": "alone"})
    assert r1.json()["status"] == "QUESTION_2"
    assert r1.json()["question"]["key"] == "desire_layer"

    r2 = _submit(client, session_id, 2, {"type": "text", "content": "想搬去海边住一个月。"})
    assert r2.json()["status"] == "QUESTION_3"

    stub = _use_provider(client, GOOD_QUOTE)
    r3 = _submit(client, session_id, 3, {"type": "option", "optionKey": "someone"})
    assert r3.status_code == 200
    assert r3.json()["status"] == "COMPLETED"
    quote = r3.json()["quote"]
    assert quote["content"] == GOOD_QUOTE
    assert stub.calls == 1

    again = client.get(f"/api/sessions/{session_id}").json()
    assert again["quote"]["id"] == quote["id"]
    assert again["quote"]["content"] == quote["content"]


# E2E-02 刷新恢复
def test_e2e_02_refresh_recovery(client):
    session_id = client.post("/api/sessions").json()["sessionId"]
    _submit(client, session_id, 1, {"type": "option", "optionKey": "conflict"})

    recovered = client.get(f"/api/sessions/{session_id}")
    assert recovered.status_code == 200
    body = recovered.json()
    assert body["status"] == "QUESTION_2"
    assert body["currentRound"] == 2
    assert body["question"]["key"] == "desire_layer"

    r2 = _submit(client, session_id, 2, {"type": "option", "optionKey": "leave"})
    assert r2.status_code == 200
    r3 = _submit(client, session_id, 3, {"type": "text", "content": "答案"})
    assert r3.json()["status"] == "COMPLETED"


# E2E-03 重复提交
def test_e2e_03_duplicate_submission(client):
    session_id = client.post("/api/sessions").json()["sessionId"]

    first = _submit(client, session_id, 1, {"type": "option", "optionKey": "alone"})
    duplicate = _submit(client, session_id, 1, {"type": "option", "optionKey": "alone"})

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "ANSWER_ALREADY_EXISTS"

    next_round = _submit(client, session_id, 2, {"type": "option", "optionKey": "rest"})
    assert next_round.status_code == 200
    assert next_round.json()["status"] == "QUESTION_3"


# E2E-04 模型失败恢复
def test_e2e_04_model_failure_recovery(client):
    session_id = client.post("/api/sessions").json()["sessionId"]
    _submit(client, session_id, 1, {"type": "option", "optionKey": "alone"})
    _submit(client, session_id, 2, {"type": "option", "optionKey": "rest"})

    stub = _use_provider(client, INVALID_SAMPLES["forbidden"], INVALID_SAMPLES["forbidden"])
    r3 = _submit(client, session_id, 3, {"type": "text", "content": "答案"})
    assert r3.status_code == 502
    assert r3.json()["error"]["code"] == "GENERATION_FAILED"
    assert r3.json()["error"]["retryable"] is True
    assert stub.calls == 2

    failed_state = client.get(f"/api/sessions/{session_id}").json()
    assert failed_state["status"] == "FAILED"

    _use_provider(client, GOOD_QUOTE)
    retry = client.post(f"/api/sessions/{session_id}/retry")
    assert retry.status_code == 200
    assert retry.json()["status"] == "COMPLETED"
    assert retry.json()["quote"]["content"] == GOOD_QUOTE


# E2E-05 输出不合格
@pytest.mark.parametrize("sample", INVALID_SAMPLES.values(), ids=INVALID_SAMPLES.keys())
def test_e2e_05_invalid_output_boundary(client, sample):
    session_id = client.post("/api/sessions").json()["sessionId"]
    _submit(client, session_id, 1, {"type": "option", "optionKey": "alone"})
    _submit(client, session_id, 2, {"type": "option", "optionKey": "rest"})

    stub = _use_provider(client, sample, sample)
    response = _submit(client, session_id, 3, {"type": "text", "content": "答案"})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "GENERATION_FAILED"
    assert stub.calls == 2
    state = client.get(f"/api/sessions/{session_id}").json()
    assert state["status"] == "FAILED"


def test_e2e_timeout_boundary(client):
    session_id = client.post("/api/sessions").json()["sessionId"]
    _submit(client, session_id, 1, {"type": "option", "optionKey": "alone"})
    _submit(client, session_id, 2, {"type": "option", "optionKey": "rest"})

    timeout = ModelCallError("MODEL_TIMEOUT", "模型调用超时")
    stub = _use_provider(client, timeout, timeout)
    response = _submit(client, session_id, 3, {"type": "text", "content": "答案"})

    assert response.status_code == 502
    assert stub.calls == 2


def test_openapi_contract(client):
    schema = client.get("/openapi.json").json()

    paths = schema["paths"]
    expected = {
        "/api/sessions": {"post"},
        "/api/sessions/{session_id}": {"get"},
        "/api/sessions/{session_id}/answers": {"post"},
        "/api/sessions/{session_id}/retry": {"post"},
        "/api/health": {"get"},
    }
    for path, methods in expected.items():
        assert path in paths, f"缺少契约路径 {path}"
        for method in methods:
            assert method in paths[path], f"{path} 缺少 {method}"

    assert "SessionOut" in schema["components"]["schemas"]
    assert "SubmitAnswerRequest" in schema["components"]["schemas"]
