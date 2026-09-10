"""会话应用服务：组装对外响应、按状态决定返回内容。

不包含路由、数据库连接或模型调用细节。
"""

from sqlalchemy.orm import Session as OrmSession

from app.models import Quote, QuoteStatus, Session
from app.questions import QuestionsConfig
from app.schemas import OptionOut, QuestionOut, QuoteOut, SessionOut, SessionStatus


def question_out(config: QuestionsConfig, round_no: int) -> QuestionOut:
    question = config.by_round(round_no)
    return QuestionOut(
        key=question.key,
        text=question.text,
        options=[OptionOut(key=o.key, label=o.label) for o in question.options],
        allow_free_text=question.allow_free_text,
    )


def build_session_out(
    config: QuestionsConfig,
    row: Session,
    quote: Quote | None = None,
) -> SessionOut:
    """按会话状态决定前端拿到的内容，前端无需猜测下一步。"""
    status = SessionStatus(row.status)
    question = None
    quote_out = None

    if status in (SessionStatus.QUESTION_1, SessionStatus.QUESTION_2, SessionStatus.QUESTION_3):
        question = question_out(config, row.current_round)
    elif status is SessionStatus.COMPLETED:
        if quote is None or quote.status is not QuoteStatus.SUCCEEDED or not quote.content:
            raise RuntimeError(f"COMPLETED 会话缺少成功金句: {row.id}")
        quote_out = QuoteOut(id=quote.id, content=quote.content)
    # GENERATING / FAILED：仅返回状态本身

    return SessionOut(
        session_id=row.id,
        status=status,
        current_round=row.current_round,
        question=question,
        quote=quote_out,
    )


def create_session(db: OrmSession, config: QuestionsConfig) -> Session:
    from app import repository as repo

    return repo.create_session(db, status=SessionStatus.QUESTION_1.value, current_round=1)


def load_session_state(db: OrmSession, config: QuestionsConfig, session_id: str) -> SessionOut:
    from app import repository as repo

    row = repo.get_session(db, session_id)
    if row is None:
        return None
    quote = repo.get_quote(db, session_id)
    return build_session_out(config, row, quote)
