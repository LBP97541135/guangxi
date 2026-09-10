"""三轮对话流程：轮次校验、回答校验、状态推进。

状态迁移边界：
    QUESTION_1 + round 1 -> QUESTION_2
    QUESTION_2 + round 2 -> QUESTION_3
    QUESTION_3 + round 3 -> GENERATING
    其他组合 -> ROUND_MISMATCH 或 INVALID_SESSION_STATE

轮次判断在后端完成，不信任前端状态；保存答案与推进状态在同一事务。
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from app import repository as repo
from app.config import Settings
from app.error_codes import (
    ANSWER_ALREADY_EXISTS,
    ANSWER_TOO_LONG,
    GENERATION_FAILED,
    INVALID_ANSWER,
    INVALID_SESSION_STATE,
    ROUND_MISMATCH,
    SESSION_NOT_FOUND,
)
from app.errors import ApiError
from app.models import Session as SessionRow
from app.questions import QuestionDef, QuestionsConfig
from app.schemas import AnswerIn, SessionOut, SessionStatus
from app.services import generation, session_service
from app.services.generation import QuoteGenerationError
from app.services.session_service import OPEN_STATES

_TRANSITIONS: dict[int, tuple[SessionStatus, int]] = {
    1: (SessionStatus.QUESTION_2, 2),
    2: (SessionStatus.QUESTION_3, 3),
    3: (SessionStatus.GENERATING, 3),
}


class FlowService:
    def __init__(
        self,
        settings: Settings,
        questions: QuestionsConfig,
        generation_service: generation.QuoteGenerationService,
    ) -> None:
        self.settings = settings
        self.questions = questions
        self.generation = generation_service

    def submit_answer(self, db: OrmSession, session_id: str, round_no: int, answer: AnswerIn) -> SessionOut:
        row = repo.get_session(db, session_id)
        if row is None:
            raise ApiError(status_code=404, code=SESSION_NOT_FOUND, message="会话不存在或已失效")

        status = SessionStatus(row.status)
        if status not in OPEN_STATES:
            raise ApiError(
                status_code=409,
                code=INVALID_SESSION_STATE,
                message="当前会话不能继续提交回答",
            )
        if repo.get_answer(db, session_id, round_no) is not None:
            raise ApiError(
                status_code=409,
                code=ANSWER_ALREADY_EXISTS,
                message="这一轮的回答已存在",
            )
        if round_no != row.current_round:
            raise ApiError(
                status_code=409,
                code=ROUND_MISMATCH,
                message=f"当前应回答第 {row.current_round} 轮",
            )

        question = session_service.resolve_active_question(self.questions, row)
        answer_type, option_key, content = self._validate_answer(question, answer)

        try:
            repo.add_answer(
                db, session_id, round_no, answer_type, option_key, content,
                question_key=question.key,
            )
        except IntegrityError as exc:
            raise ApiError(
                status_code=409,
                code=ANSWER_ALREADY_EXISTS,
                message="这一轮的回答已存在",
            ) from exc

        next_status, next_round = _TRANSITIONS[round_no]
        repo.update_session_state(db, row, next_status.value, next_round)
        if next_status in OPEN_STATES:
            repo.set_active_question(db, row, self.questions.default_for_round(next_round).key)

        if round_no == 3:
            try:
                self.generation.run(db, row)
            except QuoteGenerationError as exc:
                raise ApiError(
                    status_code=502,
                    code=GENERATION_FAILED,
                    message="金句生成失败，请重试",
                    retryable=True,
                ) from exc

        return session_service.load_session_state(db, self.questions, session_id)

    def _validate_answer(self, question: QuestionDef, answer: AnswerIn) -> tuple[str, str | None, str | None]:
        if answer.type == "option":
            if not any(option.key == answer.option_key for option in question.options):
                raise ApiError(
                    status_code=422,
                    code=INVALID_ANSWER,
                    message="所选选项不属于当前问题",
                )
            return "option", answer.option_key, None

        if not question.allow_free_text:
            raise ApiError(status_code=422, code=INVALID_ANSWER, message="当前问题不支持自由输入")

        content = answer.content.strip()
        max_chars = self.settings.answer_max_chars
        if len(content) > max_chars:
            raise ApiError(
                status_code=422,
                code=ANSWER_TOO_LONG,
                message=f"自由回答不能超过 {max_chars} 字",
            )
        return "text", None, content
