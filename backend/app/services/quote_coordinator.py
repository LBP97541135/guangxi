"""金句生成协调服务：把三轮会话链路与模型链路汇合。

职责边界：
- 三轮答案不完整时绝不调用模型。
- 每次用户生成动作最多调用模型两次（自动重试一次）。
- 成功：Quote SUCCEEDED + Session COMPLETED（随请求事务提交）。
- 失败：Quote FAILED + Session FAILED + 三轮答案保留，显式提交后抛出
  QuoteGenerationError——失败状态必须落库，同时接口要返回业务错误，
  因此这里不依赖请求结束时的统一提交。
"""

import logging

from sqlalchemy.orm import Session as OrmSession

from app import repository as repo
from app.error_codes import GENERATION_FAILED, INVALID_SESSION_STATE, SESSION_NOT_FOUND
from app.errors import ApiError
from app.llm.provider import ModelCallError, QuoteProvider, QuoteRequest
from app.llm.validator import QuoteValidator
from app.models import Answer
from app.questions import QuestionsConfig
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
        questions: QuestionsConfig,
    ) -> None:
        self.provider = provider
        self.validator = validator
        self.questions = questions
        self.calls = 0

    def run(self, db: OrmSession, session_row) -> None:
        answers = repo.list_answers(db, session_row.id)
        if len(answers) != 3:
            raise RuntimeError(f"会话 {session_row.id} 三轮答案不完整，拒绝调用模型")

        prompt_questions = tuple(self._question_text_for(answer) for answer in answers)
        prompt_answers = tuple(self._answer_text(answer) for answer in answers)

        quote = repo.ensure_quote(db, session_row.id, model=None)
        last_reason = "unknown"
        candidate_model = None

        for _ in range(MAX_PROVIDER_CALLS):
            self.calls += 1
            repo.count_attempts(quote)
            try:
                candidate = self.provider.generate(
                    QuoteRequest(questions=prompt_questions, answers=prompt_answers)
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
                repo.update_session_state(
                    db, session_row, SessionStatus.COMPLETED.value, 3
                )
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

        repo.update_session_state(db, row, SessionStatus.GENERATING.value, 3)
        try:
            self.run(db, row)
        except QuoteGenerationError as exc:
            raise ApiError(
                status_code=502,
                code=GENERATION_FAILED,
                message="金句生成失败，请重试",
                retryable=True,
            ) from exc
        return session_service.load_session_state(db, self.questions, session_id)

    def _finalize_failure(
        self,
        db: OrmSession,
        session_row,
        quote,
        model: str | None,
        reason: str,
    ) -> None:
        repo.mark_quote_failed(db, quote, model)
        repo.update_session_state(db, session_row, SessionStatus.FAILED.value, 3)
        db.commit()
        logger.warning(
            "quote generation failed: session=%s attempts=%s reason=%s",
            session_row.id,
            quote.generation_attempts,
            reason,
        )
        raise QuoteGenerationError(reason)

    def _question_text_for(self, answer: Answer) -> str:
        """Prompt 里的题面必须用用户实际回答的那道题。"""
        if answer.question_key:
            try:
                return self.questions.by_key(answer.question_key).text
            except KeyError:
                pass
        return self.questions.default_for_round(answer.round_no).text

    def _answer_text(self, answer: Answer) -> str:
        if answer.answer_type == "option" and answer.option_key:
            if answer.question_key:
                try:
                    question = self.questions.by_key(answer.question_key)
                    for option in question.options:
                        if option.key == answer.option_key:
                            return option.label
                except KeyError:
                    pass
            return answer.option_key
        return answer.content or ""
