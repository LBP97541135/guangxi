import json

import httpx
import pytest

from app.llm.fake import FAKE_QUOTE, FakeQuoteProvider
from app.llm.openai_provider import OpenAIProtocolProvider
from app.llm.prompt import PromptBuilder
from app.llm.provider import ModelCallError, QuoteRequest

REQUEST = QuoteRequest(
    questions=("第一问？", "第二问？", "第三问？"),
    answers=("回答一", "回答二", "回答三"),
)

SECRET_KEY = "sk-test-secret-key-123"


def _provider(handler) -> OpenAIProtocolProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, timeout=0.5)
    return OpenAIProtocolProvider(
        api_key=SECRET_KEY,
        base_url="https://llm.example.com/v1",
        model="test-model",
        prompt_builder=PromptBuilder("规则"),
        client=client,
    )


def _chat_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
        request=httpx.Request("POST", "https://llm.example.com/v1/chat/completions"),
    )


def test_fake_provider_fixed_output():
    candidate = FakeQuoteProvider().generate(REQUEST)

    assert candidate.text == FAKE_QUOTE
    assert candidate.model == "fake"
    assert candidate.text.startswith("其实，你")


def test_real_provider_success_parses_content():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert request.headers["Authorization"] == f"Bearer {SECRET_KEY}"
        return _chat_response("其实，你比自己想象的更勇敢。")

    candidate = _provider(handler).generate(REQUEST)

    assert candidate.text == "其实，你比自己想象的更勇敢。"
    assert candidate.model == "test-model"


def test_real_provider_timeout_maps_to_model_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(ModelCallError) as exc_info:
        _provider(handler).generate(REQUEST)

    assert exc_info.value.code == "MODEL_TIMEOUT"


def test_real_provider_http_error_hides_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    with pytest.raises(ModelCallError) as exc_info:
        _provider(handler).generate(REQUEST)

    assert exc_info.value.code == "MODEL_ERROR"
    assert SECRET_KEY not in str(exc_info.value)
    assert SECRET_KEY not in exc_info.value.message


def test_real_provider_malformed_response_is_model_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True}, request=request)

    with pytest.raises(ModelCallError) as exc_info:
        _provider(handler).generate(REQUEST)

    assert exc_info.value.code == "MODEL_ERROR"


def test_real_provider_empty_content_is_model_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return _chat_response("   ")

    with pytest.raises(ModelCallError) as exc_info:
        _provider(handler).generate(REQUEST)

    assert exc_info.value.code == "MODEL_ERROR"
