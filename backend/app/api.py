"""API 路由。路由层只做参数接收和服务调用，不含业务逻辑。"""

from typing import Generator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session as OrmSession

from app.error_codes import SESSION_NOT_FOUND
from app.errors import ApiError
from app.models import Session as SessionRow
from app.schemas import CreateSessionRequest, SessionOut, SubmitAnswerRequest
from app.services import session_service

router = APIRouter()


def get_db(request: Request) -> Generator[OrmSession, None, None]:
    factory = request.app.state.session_factory
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_questions(request: Request):
    return request.app.state.questions


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post(
    "/sessions",
    status_code=201,
    response_model=SessionOut,
    summary="创建会话并返回第一问",
)
def create_session(
    body: CreateSessionRequest | None = None,
    db: OrmSession = Depends(get_db),
    questions=Depends(get_questions),
) -> SessionOut:
    row = session_service.create_session(db, questions)
    return session_service.load_session_state(db, questions, row.id)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionOut,
    summary="获取会话当前进度或最终金句",
    responses={404: {"description": "会话不存在"}},
)
def get_session(
    session_id: str,
    db: OrmSession = Depends(get_db),
    questions=Depends(get_questions),
) -> SessionOut:
    out = session_service.load_session_state(db, questions, session_id)
    if out is None:
        raise ApiError(status_code=404, code=SESSION_NOT_FOUND, message="会话不存在或已失效")
    return out


@router.post(
    "/sessions/{session_id}/answers",
    response_model=SessionOut,
    summary="提交当前轮答案；第三轮后生成金句",
    responses={404: {"description": "会话不存在"}},
)
def submit_answer(
    session_id: str,
    body: SubmitAnswerRequest,
    request: Request,
    db: OrmSession = Depends(get_db),
) -> SessionOut:
    flow = request.app.state.flow_service
    return flow.submit_answer(db, session_id, body.round, body.answer)
