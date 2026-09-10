"""最小数据访问函数。只做读写，不提交事务、不含 HTTP 与模型调用逻辑。

事务边界由服务层控制：调用方在业务事务完成后统一 commit。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models import Answer, Quote, QuoteStatus, Session


def create_session(db: OrmSession, status: str, current_round: int, active_question_key: str | None = None) -> Session:
    row = Session(status=status, current_round=current_round, active_question_key=active_question_key)
    db.add(row)
    db.flush()
    return row


def get_session(db: OrmSession, session_id: str) -> Session | None:
    return db.get(Session, session_id)


def update_session_state(db: OrmSession, session: Session, status: str, current_round: int) -> None:
    session.status = status
    session.current_round = current_round
    db.flush()


def set_active_question(db: OrmSession, session: Session, question_key: str) -> None:
    session.active_question_key = question_key
    db.flush()


def get_answer(db: OrmSession, session_id: str, round_no: int) -> Answer | None:
    return db.scalar(
        select(Answer).where(Answer.session_id == session_id, Answer.round_no == round_no)
    )


def add_answer(
    db: OrmSession,
    session_id: str,
    round_no: int,
    answer_type: str,
    option_key: str | None,
    content: str | None,
    question_key: str | None = None,
) -> Answer:
    row = Answer(
        session_id=session_id,
        round_no=round_no,
        question_key=question_key,
        answer_type=answer_type,
        option_key=option_key,
        content=content,
    )
    db.add(row)
    db.flush()
    return row


def list_answers(db: OrmSession, session_id: str) -> list[Answer]:
    return list(
        db.scalars(
            select(Answer).where(Answer.session_id == session_id).order_by(Answer.round_no)
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
