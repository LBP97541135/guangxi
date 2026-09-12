"""API 路由。路由层只做参数接收和服务调用，不含业务逻辑。
"""

from typing import Generator

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session as OrmSession

from app.database import make_session_factory
from app.error_codes import SESSION_NOT_FOUND
from app.errors import ApiError
from app.models import Session as SessionRow
from app.schemas import (
    CreateSessionRequest,
    EndRequest,
    SessionOut,
    SubmitMessageRequest,
)
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


def _run_generation_in_background(session_id: str, request: Request) -> None:
    """BackgroundTasks 入口：在新事务里跑 generation，失败也不抛回 HTTP。"""
    factory = request.app.state.session_factory
    db = factory()
    try:
        request.app.state.flow_service.run_generation(db, session_id)
        db.commit()
    except Exception:
        db.rollback()
        # generation.run 自己会落 FAILED；这里只兜底
    finally:
        db.close()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post(
    "/sessions",
    status_code=201,
    response_model=SessionOut,
    summary="创建会话并返回 guide 开场白",
)
def create_session(
    body: CreateSessionRequest | None = None,
    db: OrmSession = Depends(get_db),
) -> SessionOut:
    row = session_service.create_session(db)
    return session_service.load_session_state(db, row.id)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionOut,
    summary="获取会话当前状态（OPEN_CHAT / GENERATING / COMPLETED / FAILED）+ 消息历史 + 金句",
    responses={404: {"description": "会话不存在"}},
)
def get_session(session_id: str, db: OrmSession = Depends(get_db)) -> SessionOut:
    out = session_service.load_session_state(db, session_id)
    if out is None:
        raise ApiError(status_code=404, code=SESSION_NOT_FOUND, message="会话不存在或已失效")
    return out


@router.post(
    "/sessions/{session_id}/messages",
    response_model=SessionOut,
    summary="追加一条用户消息（开放式聊天，不限次数）",
    responses={404: {"description": "会话不存在"}},
)
def submit_message(
    session_id: str,
    body: SubmitMessageRequest,
    request: Request,
    db: OrmSession = Depends(get_db),
) -> SessionOut:
    flow = request.app.state.flow_service
    return flow.submit_message(db, session_id, body.message)


@router.post(
    "/sessions/{session_id}/end",
    response_model=SessionOut,
    summary="用户主动收束本次相遇，触发远行鼓励生成（异步）",
    responses={404: {"description": "会话不存在"}, 409: {"description": "会话状态不允许结束"}},
)
def end_conversation(
    session_id: str,
    body: EndRequest,
    background: BackgroundTasks,
    request: Request,
    db: OrmSession = Depends(get_db),
) -> SessionOut:
    flow = request.app.state.flow_service
    def runner(sid: str) -> None:
        _run_generation_in_background(sid, request)
    return flow.end_conversation(db, session_id, body.end_kind, runner)


@router.post(
    "/sessions/{session_id}/retry",
    response_model=SessionOut,
    summary="生成失败后重新尝试（异步）",
    responses={404: {"description": "会话不存在"}, 409: {"description": "会话状态不允许重试"}},
)
def retry_generation(
    session_id: str,
    background: BackgroundTasks,
    request: Request,
    db: OrmSession = Depends(get_db),
) -> SessionOut:
    coordinator = request.app.state.generation_service
    # 切到 GENERATING 再交给后台跑
    row = db.get(SessionRow, session_id)
    if row is None:
        raise ApiError(status_code=404, code=SESSION_NOT_FOUND, message="会话不存在或已失效")
    from app import repository as repo
    from app.schemas import SessionStatus
    repo.update_session_state(db, row, SessionStatus.GENERATING.value)
    db.commit()
    background.add_task(_run_generation_in_background, session_id, request)
    return session_service.load_session_state(db, session_id)


@router.post(
    "/sessions/{session_id}/regenerate",
    response_model=SessionOut,
    summary="已完成的金句重新生成（更温柔 / 更有力量 / 默认）",
    responses={404: {"description": "会话不存在"}, 409: {"description": "会话未完成"}},
)
def regenerate(
    session_id: str,
    body: dict,  # {tone: 'softer'|'stronger'|None}
    request: Request,
    db: OrmSession = Depends(get_db),
) -> SessionOut:
    coordinator = request.app.state.generation_service
    tone = body.get("tone") if isinstance(body, dict) else None
    if tone not in (None, "softer", "stronger"):
        tone = None
    return coordinator.regenerate(db, session_id, tone_hint=tone)

