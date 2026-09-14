"""开放式聊天：用户消息后向导回复落库。"""

from fastapi.testclient import TestClient


def _create_session(client: TestClient) -> str:
    r = client.post("/api/sessions", json={})
    assert r.status_code == 201
    return r.json()["sessionId"]


def test_submit_message_returns_guide_reply(client: TestClient):
    sid = _create_session(client)
    r = client.post(
        f"/api/sessions/{sid}/messages",
        json={"message": {"content": "最近换工作，心里没底"}},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "OPEN_CHAT"
    roles = [m["role"] for m in out["messages"]]
    # 开场白(guide) → 用户 → 向导回复(guide)
    assert roles == ["guide", "user", "guide"]
    assert out["messages"][2]["content"]
    assert out["messages"][2]["seq"] == 3


def test_guide_reply_persists_across_get(client: TestClient):
    sid = _create_session(client)
    client.post(
        f"/api/sessions/{sid}/messages",
        json={"message": {"content": "嗯"}},
    )
    r = client.get(f"/api/sessions/{sid}")
    roles = [m["role"] for m in r.json()["messages"]]
    assert roles == ["guide", "user", "guide"]
