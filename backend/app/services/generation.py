"""金句生成服务接口。

第三轮完成后由流程服务调用。实现方负责把生成结果与状态在同一事务内落库：
- 成功：Quote 置为 SUCCEEDED，Session 置为 COMPLETED。
- 失败：实现方自行记录失败状态后抛出 QuoteGenerationError。

T05 提供 Fake 实现；T07 以真实协调服务替换，接口形状不变。
"""

from typing import Protocol

from sqlalchemy.orm import Session as OrmSession

from app import repository as repo
from app.models import Session as SessionRow
from app.schemas import SessionStatus

FAKE_QUOTE = "其实，你只是还没和自己好好和解。"


class QuoteGenerationError(Exception):
    """生成最终失败（含自动重试后仍失败）。调用方应将会话保持/置为 FAILED。"""


class QuoteGenerationService(Protocol):
    def run(self, db: OrmSession, session_row: SessionRow) -> None: ...


class FakeQuoteGenerationService:
    """不联网的固定输出，用于跑通全流程与前端联调。"""

    def __init__(self) -> None:
        self.calls = 0

    def run(self, db: OrmSession, session_row: SessionRow) -> None:
        self.calls += 1
        quote = repo.ensure_quote(db, session_row.id, model="fake")
        repo.mark_quote_succeeded(db, quote, FAKE_QUOTE, model="fake")
        repo.update_session_state(db, session_row, SessionStatus.COMPLETED.value, 3)
