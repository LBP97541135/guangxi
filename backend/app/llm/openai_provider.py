"""OpenAI 协议真实 Provider。

任何兼容 OpenAI Chat Completions 的服务均可通过环境变量接入：
MODEL_API_KEY / MODEL_BASE_URL / MODEL_NAME。不硬编码供应商。
"""

import re

import httpx

from app.llm.prompt import PromptBuilder
from app.llm.provider import (
    GenerationCandidate,
    ModelCallError,
    QuoteRequest,
    map_httpx_error,
)

THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class OpenAIProtocolProvider:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        prompt_builder: PromptBuilder,
        timeout_seconds: float = 15.0,
        max_tokens: int = 3000,
        client: httpx.Client | None = None,
        reasoning_effort: str | None = None,
        chat_system_rules: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompt_builder = prompt_builder
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.chat_system_rules = chat_system_rules
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def generate(self, request: QuoteRequest) -> GenerationCandidate:
        payload = {
            "model": self.model,
            "messages": self.prompt_builder.build_messages(
                list(request.user_messages), request.end_kind, request.tone_hint
            ),
            "temperature": 0.7,
            "max_tokens": self.max_tokens,  # 推理模型的思考也会计入，留足余量
            "stream": False,
        }
        if self.reasoning_effort:
            # OpenAI 协议标准字段；推理模型用它控制思考档位，普通模型/网关可留空不发送
            payload["reasoning_effort"] = self.reasoning_effort
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise map_httpx_error(exc) from exc

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise ModelCallError("MODEL_ERROR", "模型响应格式异常") from exc

        # 推理模型会把 CoT 直接写进 content，先剥掉 <think>...</think> 再交给 validator。
        text = THINK_BLOCK.sub("", content or "").strip()
        if not text:
            raise ModelCallError("MODEL_ERROR", "模型返回空内容")
        return GenerationCandidate(text=text, model=self.model)

    def generate_chat_reply(self, history: list[dict]) -> str:
        """对话中的向导回复。history 是 [{"role": "user"|"guide", "content": str}, ...] 按 seq 排序。"""
        if not self.chat_system_rules:
            raise ModelCallError("MODEL_ERROR", "未配置对话回复 prompt")
        messages = [{"role": "system", "content": self.chat_system_rules}]
        for item in history:
            role = "assistant" if item["role"] == "guide" else "user"
            messages.append({"role": role, "content": item["content"]})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 200,
            "stream": False,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        try:
            response = self._client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise map_httpx_error(exc) from exc

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise ModelCallError("MODEL_ERROR", "模型响应格式异常") from exc

        text = THINK_BLOCK.sub("", content or "").strip()
        # 推理模型可能只输出思考没有正文，兜底一句陪伴语
        return text or "嗯，我在听。"
