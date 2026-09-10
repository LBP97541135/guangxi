"""FastAPI 应用入口。"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import api
from app.config import Settings, get_settings
from app.errors import ApiError, api_error_handler, unhandled_error_handler
from app.log import setup_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging()

    app = FastAPI(
        title="光隙 API",
        description="三轮对话与金句生成 Demo 后端",
        version="0.1.0",
    )
    app.state.settings = settings

    app.include_router(api.router, prefix="/api")

    if settings.allow_cors_origins:
        origins = [o.strip() for o in settings.allow_cors_origins.split(",") if o.strip()]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    return app


async def validation_error_handler(request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "INVALID_PARAMS", "message": "请求参数不合法", "retryable": False}},
    )


app = create_app()
