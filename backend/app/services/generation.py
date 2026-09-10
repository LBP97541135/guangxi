"""金句生成服务接口。

第三轮完成后由流程服务调用。实现方负责把生成结果与状态在同一事务内落库：
- 成功：Quote 置为 SUCCEEDED，Session 置为 COMPLETED。
- 失败：实现方自行把失败状态落库后抛出 QuoteGenerationError。

真实实现见 services/quote_coordinator.py。
"""

from typing import Protocol

from sqlalchemy.orm import Session as OrmSession

from app.models import Session as SessionRow


class QuoteGenerationError(Exception):
    """生成最终失败（含自动重试后仍失败）。失败状态已由实现方落库。"""


class QuoteGenerationService(Protocol):
    def run(self, db: OrmSession, session_row: SessionRow) -> None: ...
