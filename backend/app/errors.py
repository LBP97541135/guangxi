"""统一错误响应结构。

所有业务错误抛出 ApiError，由全局异常处理器转换为：

    {"error": {"code": "...", "message": "...", "retryable": false}}
"""

import logging
from dataclasses import dataclass, field

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    retryable: bool = False
    headers: dict = field(default_factory=dict)

    def to_body(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
            }
        }


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    logger.warning(
        "business error: %s %s -> %s",
        request.method,
        request.url.path,
        exc.code,
        extra={"path": request.url.path, "method": request.method, "error_code": exc.code},
    )
    return JSONResponse(status_code=exc.status_code, content=exc.to_body(), headers=exc.headers or None)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "服务器内部错误", "retryable": False}},
    )
