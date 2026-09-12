"""会话应用服务：组装对外响应、按状态决定返回内容。

开放式聊天，没有"轮"的概念，会话只关心：
- 当前阶段：OPEN_CHAT / GENERATING / COMPLETED / FAILED
- 消息历史：guide 的开场白 + 用户的若干条
- 收束方式：end_kind（用于 Prompt 注入）
- 金句：成功才有
"""

from sqlalchemy.orm import Session as OrmSession

from app import repository as repo
from app.models import Quote, QuoteStatus, Session
from app.schemas import (
    MessageOut,
    QuoteOut,
    SessionOut,
    SessionStatus,
)

OPEN_STATES = (SessionStatus.OPEN_CHAT,)

GUIDE_OPENING = "最近，有什么事一直挂在心上吗？不用组织得很完整，想到哪里说到哪里。"


def build_session_out(
    row: Session,
    quote: Quote | None = None,
    messages: list | None = None,
) -> SessionOut:
    """按会话状态组装对外响应。messages 总是返回（OPEN_CHAT 时是历史；COMPLETED 时也可回放）。"""
    status = SessionStatus(row.status)
    quote_out = None

    if status is SessionStatus.COMPLETED:
        if quote is None or quote.status is not QuoteStatus.SUCCEEDED or not quote.content:
            raise RuntimeError(f"COMPLETED 会话缺少成功金句: {row.id}")
        quote_out = QuoteOut(id=quote.id, content=quote.content)

    msg_out = [
        MessageOut(seq=m.seq, role=m.role, content=m.content, created_at=m.created_at.isoformat())
        for m in (messages or [])
    ]

    return SessionOut(
        session_id=row.id,
        status=status,
        end_kind=row.end_kind,
        messages=msg_out,
        quote=quote_out,
    )


def create_session(db: OrmSession) -> Session:
    """新会话：状态 OPEN_CHAT，开场白作为第一条 guide 消息存进去。"""
    row = repo.create_session(db, status=SessionStatus.OPEN_CHAT.value)
    repo.add_message(db, row.id, seq=1, role="guide", content=GUIDE_OPENING)
    return row


def load_session_state(db: OrmSession, session_id: str) -> SessionOut | None:
    row = repo.get_session(db, session_id)
    if row is None:
        return None
    quote = repo.get_quote(db, session_id)
    messages = repo.list_messages(db, session_id)
    return build_session_out(row, quote=quote, messages=messages)
