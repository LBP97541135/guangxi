"""开放式聊天流程：用户消息追加、收束时触发金句生成。

状态迁移边界：
    OPEN_CHAT + user message        → OPEN_CHAT (追加)
    OPEN_CHAT + user end (任意 kind) → GENERATING（异步生成）
    GENERATING                       → COMPLETED / FAILED（由 coordinator 决定）

end_conversation 立即返回 GENERATING 状态；金句生成跑在 FastAPI 后台任务里，
前端轮询 GET /sessions/{id} 拿最终结果。
"""

from sqlalchemy.orm import Session as OrmSession

from app import repository as repo
from app.error_codes import (
    ANSWER_TOO_LONG,
    GENERATION_FAILED,
    INVALID_SESSION_STATE,
    SESSION_NOT_FOUND,
)
from app.errors import ApiError
from app.models import Session as SessionRow
from app.schemas import EndKind, MessageIn, SessionOut, SessionStatus
from app.services import session_service
from app.services.generation import QuoteGenerationError


OPEN_STATES = (SessionStatus.OPEN_CHAT,)


class FlowService:
    def __init__(self, settings, generation_service):
        self.settings = settings
        self.generation = generation_service

    def submit_message(
        self, db: OrmSession, session_id: str, message: MessageIn
    ) -> SessionOut:
        row = repo.get_session(db, session_id)
        if row is None:
            raise ApiError(status_code=404, code=SESSION_NOT_FOUND, message="会话不存在或已失效")

        if SessionStatus(row.status) not in OPEN_STATES:
            raise ApiError(
                status_code=409,
                code=INVALID_SESSION_STATE,
                message="当前会话不能继续发消息",
            )

        content = message.content.strip()
        max_chars = self.settings.answer_max_chars
        if len(content) > max_chars:
            raise ApiError(
                status_code=422,
                code=ANSWER_TOO_LONG,
                message=f"消息不能超过 {max_chars} 字",
            )

        seq = repo.next_message_seq(db, session_id)
        repo.add_message(db, session_id, seq, role="user", content=content)
        db.commit()

        return session_service.load_session_state(db, session_id)

    def end_conversation(
        self, db: OrmSession, session_id: str, end_kind: EndKind, background_runner
    ) -> SessionOut:
        """立即把状态切到 GENERATING，把生成任务交给 background_runner。
        background_runner 接受 (db_factory, session_id) 两个参数，并在它自己的事务里跑 generation.run。
        """
        row = repo.get_session(db, session_id)
        if row is None:
            raise ApiError(status_code=404, code=SESSION_NOT_FOUND, message="会话不存在或已失效")

        status = SessionStatus(row.status)
        if status not in (SessionStatus.OPEN_CHAT, SessionStatus.FAILED):
            raise ApiError(
                status_code=409,
                code=INVALID_SESSION_STATE,
                message="当前会话已收束，无需再结束",
            )

        repo.update_session_state(
            db, row, SessionStatus.GENERATING.value, end_kind=end_kind.value
        )
        db.commit()

        # 异步执行生成（在自己的事务里），不要在请求线程里阻塞
        background_runner(session_id)

        return session_service.load_session_state(db, session_id)

    def run_generation(self, db: OrmSession, session_id: str) -> None:
        """后台任务入口：调 generation.run，成功或失败都已落库。"""
        row = repo.get_session(db, session_id)
        if row is None:
            return
        try:
            self.generation.run(db, row)
        except QuoteGenerationError:
            # generation.run 自己负责落 FAILED 状态
            pass
