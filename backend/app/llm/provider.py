"""QuoteProvider 抽象与内部模型错误。

供应商异常一律转换为 ModelCallError，不向路由层泄露 SDK/HTTP 细节与密钥。
"""

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.error_codes import MODEL_ERROR, MODEL_TIMEOUT


@dataclass(frozen=True)
class QuoteRequest:
    """三个有序问题与三个有序回答。"""

    questions: tuple[str, str, str]
    answers: tuple[str, str, str]


@dataclass(frozen=True)
class GenerationCandidate:
    text: str
    model: str


class ModelCallError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class QuoteProvider(Protocol):
    def generate(self, request: QuoteRequest) -> GenerationCandidate: ...


def map_httpx_error(exc: httpx.HTTPError) -> ModelCallError:
    if isinstance(exc, (httpx.TimeoutException,)):
        return ModelCallError(MODEL_TIMEOUT, "模型调用超时")
    if isinstance(exc, httpx.HTTPStatusError):
        return ModelCallError(MODEL_ERROR, f"模型服务返回异常状态 {exc.response.status_code}")
    return ModelCallError(MODEL_ERROR, "模型服务连接失败")
