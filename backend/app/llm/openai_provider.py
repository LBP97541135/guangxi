"""OpenAI 协议真实 Provider。

任何兼容 OpenAI Chat Completions 的服务均可通过环境变量接入：
MODEL_API_KEY / MODEL_BASE_URL / MODEL_NAME。不硬编码供应商。
"""

import httpx

from app.llm.prompt import PromptBuilder
from app.llm.provider import (
    GenerationCandidate,
    ModelCallError,
    QuoteRequest,
    map_httpx_error,
)


class OpenAIProtocolProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        prompt_builder: PromptBuilder,
        timeout_seconds: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompt_builder = prompt_builder
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def generate(self, request: QuoteRequest) -> GenerationCandidate:
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": self.prompt_builder.build_messages(request),
                    "temperature": 0.9,
                    "max_tokens": 200,
                    "stream": False,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise map_httpx_error(exc) from exc

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise ModelCallError("MODEL_ERROR", "模型响应格式异常") from exc

        text = (content or "").strip()
        if not text:
            raise ModelCallError("MODEL_ERROR", "模型返回空内容")
        return GenerationCandidate(text=text, model=self.model)
