"""FastAPI 应用入口。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import api
from app.config import Settings, get_settings
from app.database import create_engine_from_url, init_db, make_session_factory
from app.error_codes import INVALID_PARAMS
from app.errors import ApiError, api_error_handler, unhandled_error_handler
from app.llm.fake import FakeQuoteProvider
from app.llm.openai_provider import OpenAIProtocolProvider
from app.llm.prompt import PromptBuilder, load_system_rules
from app.llm.validator import QuoteValidator
from app.log import setup_logging
from app.services.flow_service import FlowService
from app.services.quote_coordinator import QuoteGenerationCoordinator


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging()

    app = FastAPI(
        title="光隙 API",
        description="开放式聊天 + 远行鼓励生成 Demo 后端",
        version="0.2.0",
    )
    app.state.settings = settings

    engine = create_engine_from_url(settings.database_url)
    init_db(engine)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    prompt_builder = PromptBuilder(load_system_rules(settings.prompt_file))
    chat_provider: object
    if settings.model_provider == "real":
        if not settings.model_api_key or not settings.model_name:
            raise RuntimeError("MODEL_PROVIDER=real 需要配置 MODEL_API_KEY 与 MODEL_NAME")
        provider = OpenAIProtocolProvider(
            api_key=settings.model_api_key,
            base_url=settings.model_base_url or "https://api.openai.com/v1",
            model=settings.model_name,
            prompt_builder=prompt_builder,
            timeout_seconds=settings.model_timeout_seconds,
            max_tokens=settings.model_max_tokens,
            reasoning_effort=settings.model_reasoning_effort,
            chat_system_rules=load_system_rules(settings.chat_prompt_file),
        )
        chat_provider = provider
    else:
        provider = FakeQuoteProvider()
        chat_provider = provider

    app.state.generation_service = QuoteGenerationCoordinator(
        provider=provider,
        validator=QuoteValidator(max_chars=settings.quote_max_chars),
    )
    app.state.flow_service = FlowService(
        settings=settings,
        generation_service=app.state.generation_service,
        chat_provider=chat_provider,
    )

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

    # 同仓前后端：存在 frontend/ 目录时由本进程直接托管（演示单进程部署）
    frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
    return app


async def validation_error_handler(request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": INVALID_PARAMS, "message": "请求参数不合法", "retryable": False}},
    )


app = create_app()
