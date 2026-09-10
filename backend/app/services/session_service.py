"""会话应用服务：组装对外响应、按状态决定返回内容、轮内换题。

不包含路由、数据库连接或模型调用细节。
"""

from sqlalchemy.orm import Session as OrmSession

from app import repository as repo
from app.error_codes import INVALID_SESSION_STATE, SESSION_NOT_FOUND
from app.errors import ApiError
from app.models import Quote, QuoteStatus, Session
from app.questions import QuestionDef, QuestionsConfig
from app.schemas import OptionOut, QuestionOut, QuoteOut, SessionOut, SessionStatus

OPEN_STATES = (SessionStatus.QUESTION_1, SessionStatus.QUESTION_2, SessionStatus.QUESTION_3)


def resolve_active_question(config: QuestionsConfig, row: Session) -> QuestionDef:
    """当前应展示/应答的题目：优先取会话记录的题目键（且轮次一致），否则回落默认题。"""
    if row.active_question_key:
        try:
            question = config.by_key(row.active_question_key)
            if question.round == row.current_round:
                return question
        except KeyError:
            pass
    return config.default_for_round(row.current_round)


def question_out(question: QuestionDef) -> QuestionOut:
    return QuestionOut(
        key=question.key,
        title=question.title,
        text=question.text,
        options=[OptionOut(key=o.key, label=o.label) for o in question.options],
        allow_free_text=question.allow_free_text,
        scene_example=question.scene_example,
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

    if status in OPEN_STATES:
        question = question_out(resolve_active_question(config, row))
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
    return repo.create_session(
        db,
        status=SessionStatus.QUESTION_1.value,
        current_round=1,
        active_question_key=config.default_for_round(1).key,
    )


def load_session_state(db: OrmSession, config: QuestionsConfig, session_id: str) -> SessionOut | None:
    row = repo.get_session(db, session_id)
    if row is None:
        return None
    quote = repo.get_quote(db, session_id)
    return build_session_out(config, row, quote)


def switch_question(db: OrmSession, config: QuestionsConfig, session_id: str) -> SessionOut:
    """轮内换个情境：在当前轮的题目变体中循环切换。"""
    row = repo.get_session(db, session_id)
    if row is None:
        raise ApiError(status_code=404, code=SESSION_NOT_FOUND, message="会话不存在或已失效")
    if SessionStatus(row.status) not in OPEN_STATES:
        raise ApiError(
            status_code=409,
            code=INVALID_SESSION_STATE,
            message="当前会话不能切换问题",
        )

    variants = config.variants_for_round(row.current_round)
    keys = [v.key for v in variants]
    try:
        index = keys.index(row.active_question_key)
    except ValueError:
        index = -1
    next_variant = variants[(index + 1) % len(keys)]
    repo.set_active_question(db, row, next_variant.key)

    quote = repo.get_quote(db, session_id)
    return build_session_out(config, row, quote)
