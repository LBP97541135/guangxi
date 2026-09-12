"""金句生成协调服务。

收集会话中的用户消息历史 + end_kind，调用 Provider 生成，验证后写库。
"""

import logging

from sqlalchemy.orm import Session as OrmSession

from app import repository as repo
from app.error_codes import GENERATION_FAILED, INVALID_SESSION_STATE, SESSION_NOT_FOUND
from app.errors import ApiError
from app.llm.provider import ModelCallError, QuoteProvider, QuoteRequest
from app.llm.validator import QuoteValidator
from app.models import Message, Quote, Session
from app.questions import QuestionsConfig  # noqa: F401  # 保留类型引用
from app.schemas import SessionOut, SessionStatus
from app.services import session_service
from app.services.generation import QuoteGenerationError

logger = logging.getLogger(__name__)

MAX_PROVIDER_CALLS = 2


class QuoteGenerationCoordinator:
    def __init__(
        self,
        provider: QuoteProvider,
        validator: QuoteValidator,
        questions: QuestionsConfig | None = None,  # 兼容旧构造，新版不需要
    ) -> None:
        self.provider = provider
        self.validator = validator
        self.questions = questions  # 实际不用，保留以免破坏旧调用点

    def run(self, db: OrmSession, session_row: Session) -> None:
        user_msgs = [m.content for m in repo.user_messages(db, session_row.id)]
        if not user_msgs:
            raise RuntimeError(f"会话 {session_row.id} 没有用户消息，拒绝调用模型")

        end_kind = session_row.end_kind or "natural_close"

        quote = repo.ensure_quote(db, session_row.id, model=None)
        last_reason = "unknown"
        candidate_model = None

        for _ in range(MAX_PROVIDER_CALLS):
            repo.count_attempts(quote)
            try:
                candidate = self.provider.generate(
                    QuoteRequest(
                        user_messages=user_msgs,
                        end_kind=end_kind,
                    )
                )
            except ModelCallError as exc:
                last_reason = f"model_call:{exc.code}:{exc.message}"
                logger.warning(
                    "quote generation provider error: session=%s reason=%s",
                    session_row.id,
                    last_reason,
                )
                continue

            candidate_model = candidate.model
            ok, reason = self.validator.validate(candidate.text)
            if ok:
                repo.mark_quote_succeeded(db, quote, candidate.text.strip(), candidate.model)
                repo.update_session_state(db, session_row, SessionStatus.COMPLETED.value)
                db.commit()
                return
            last_reason = f"validation:{reason}"
            logger.warning(
                "quote validation failed: session=%s reason=%s", session_row.id, reason
            )

        self._finalize_failure(db, session_row, quote, candidate_model, last_reason)

    def retry(self, db: OrmSession, session_id: str) -> SessionOut:
        row = repo.get_session(db, session_id)
        if row is None:
            raise ApiError(status_code=404, code=SESSION_NOT_FOUND, message="会话不存在或已失效")
        if row.status != SessionStatus.FAILED.value:
            raise ApiError(
                status_code=409,
                code=INVALID_SESSION_STATE,
                message="只有生成失败的会话可以重试",
            )

        repo.update_session_state(db, row, SessionStatus.GENERATING.value)
        try:
            self.run(db, row)
        except QuoteGenerationError as exc:
            raise ApiError(
                status_code=502,
                code=GENERATION_FAILED,
                message="远行鼓励还没写出来，可以再试一次",
                retryable=True,
            ) from exc
        return session_service.load_session_state(db, session_id)

    def regenerate(
        self,
        db: OrmSession,
        session_id: str,
        tone_hint: str,
    ) -> SessionOut:
        """result-stage 的「更温柔一点 / 更有力量一点」按钮触发。
        在原 user_messages 基础上追加 tone_hint 再生成。"""
        row = repo.get_session(db, session_id)
        if row is None:
            raise ApiError(status_code=404, code=SESSION_NOT_FOUND, message="会话不存在或已失效")
        if row.status != SessionStatus.COMPLETED.value:
            raise ApiError(
                status_code=409,
                code=INVALID_SESSION_STATE,
                message="只有已完成的会话可以重写金句",
            )

        # 复用 COMPLETED 状态的 quote 行（已有唯一约束），只改内容
        quote = repo.get_quote(db, session_id)
        if quote is None:
            raise RuntimeError(f"COMPLETED 会话缺少 quote 行: {session_id}")

        end_kind = row.end_kind or "natural_close"
        last_reason = "unknown"
        candidate_model = None

        for _ in range(MAX_PROVIDER_CALLS):
            repo.count_attempts(quote)
            try:
                candidate = self.provider.generate(
                    QuoteRequest(
                        user_messages=[m.content for m in repo.user_messages(db, session_id)],
                        end_kind=end_kind,
                        tone_hint=tone_hint,
                    )
                )
            except ModelCallError as exc:
                last_reason = f"model_call:{exc.code}:{exc.message}"
                logger.warning(
                    "regenerate provider error: session=%s reason=%s",
                    session_id, last_reason,
                )
                continue
            candidate_model = candidate.model
            ok, reason = self.validator.validate(candidate.text)
            if ok:
                repo.mark_quote_succeeded(db, quote, candidate.text.strip(), candidate.model)
                db.commit()
                return session_service.load_session_state(db, session_id)
            last_reason = f"validation:{reason}"

        # 重写也失败：维持原内容，把错误抛给前端显示
        logger.warning(
            "regenerate failed: session=%s reason=%s", session_id, last_reason
        )
        raise ApiError(
            status_code=502,
            code=GENERATION_FAILED,
            message="这次改写没成，可以再试一次",
            retryable=True,
        )

    def _finalize_failure(
        self,
        db: OrmSession,
        session_row: Session,
        quote: Quote,
        model: str | None,
        reason: str,
    ) -> None:
        repo.mark_quote_failed(db, quote, model)
        repo.update_session_state(db, session_row, SessionStatus.FAILED.value)
        db.commit()
        logger.warning(
            "quote generation failed: session=%s attempts=%s reason=%s",
            session_row.id,
            quote.generation_attempts,
            reason,
        )
        raise QuoteGenerationError(reason)
