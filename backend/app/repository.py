"""最小数据访问函数。只做读写，不提交事务、不含 HTTP 与模型调用逻辑。

事务边界由服务层控制：调用方在业务事务完成后统一 commit。
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.models import Message, Quote, QuoteStatus, Session


def create_session(db: OrmSession, status: str) -> Session:
    row = Session(status=status)
    db.add(row)
    db.flush()
    return row


def get_session(db: OrmSession, session_id: str) -> Session | None:
    return db.get(Session, session_id)


def update_session_state(db: OrmSession, session: Session, status: str, end_kind: str | None = None) -> None:
    session.status = status
    if end_kind is not None:
        session.end_kind = end_kind
    db.flush()


def next_message_seq(db: OrmSession, session_id: str) -> int:
    """下一个消息序号；空会话从 1 开始。"""
    current = db.scalar(
        select(func.coalesce(func.max(Message.seq), 0)).where(Message.session_id == session_id)
    )
    return int(current) + 1


def add_message(db: OrmSession, session_id: str, seq: int, role: str, content: str) -> Message:
    row = Message(session_id=session_id, seq=seq, role=role, content=content)
    db.add(row)
    db.flush()
    return row


def list_messages(db: OrmSession, session_id: str) -> list[Message]:
    return list(
        db.scalars(
            select(Message).where(Message.session_id == session_id).order_by(Message.seq)
        )
    )


def user_messages(db: OrmSession, session_id: str) -> list[Message]:
    return list(
        db.scalars(
            select(Message)
            .where(Message.session_id == session_id, Message.role == "user")
            .order_by(Message.seq)
        )
    )


def get_quote(db: OrmSession, session_id: str) -> Quote | None:
    return db.scalar(select(Quote).where(Quote.session_id == session_id))


def ensure_quote(db: OrmSession, session_id: str, model: str | None) -> Quote:
    """获取或创建 GENERATING 状态的 Quote 行；同一会话只有一条。"""
    row = get_quote(db, session_id)
    if row is None:
        row = Quote(session_id=session_id, model=model, status=QuoteStatus.GENERATING)
        db.add(row)
        db.flush()
    return row


def mark_quote_succeeded(db: OrmSession, quote: Quote, content: str, model: str | None) -> None:
    quote.content = content
    quote.model = model
    quote.status = QuoteStatus.SUCCEEDED
    db.flush()


def mark_quote_failed(db: OrmSession, quote: Quote, model: str | None) -> None:
    quote.model = model
    quote.status = QuoteStatus.FAILED
    db.flush()


def count_attempts(quote: Quote) -> int:
    quote.generation_attempts += 1
    return quote.generation_attempts
