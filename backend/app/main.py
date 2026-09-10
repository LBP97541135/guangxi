"""FastAPI 应用入口。"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import api
from app.config import Settings, get_settings
from app.database import create_engine_from_url, init_db, make_session_factory
from app.error_codes import INVALID_PARAMS
from app.errors import ApiError, api_error_handler, unhandled_error_handler
from app.log import setup_logging
from app.questions import load_questions
from app.services.flow_service import FlowService
from app.services.generation import FakeQuoteGenerationService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging()

    app = FastAPI(
        title="光隙 API",
        description="三轮对话与金句生成 Demo 后端",
        version="0.1.0",
    )
    app.state.settings = settings
    app.state.questions = load_questions(settings.questions_file)

    engine = create_engine_from_url(settings.database_url)
    init_db(engine)
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)

    app.state.generation_service = FakeQuoteGenerationService()
    app.state.flow_service = FlowService(
        settings=settings,
        questions=app.state.questions,
        generation_service=app.state.generation_service,
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
    return app


async def validation_error_handler(request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": INVALID_PARAMS, "message": "请求参数不合法", "retryable": False}},
    )


app = create_app()
