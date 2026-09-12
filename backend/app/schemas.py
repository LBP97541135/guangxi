"""前后端联调契约：会话状态、请求/响应 Schema。字段以 camelCase 输出。
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SessionStatus(str, Enum):
    OPEN_CHAT = "OPEN_CHAT"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EndKind(str, Enum):
    USER_ACTIVE = "user_active"          # 用户主动结束
    USER_STILL_TALKING = "user_still_talking"  # 用户还在犹豫
    USER_NO_WANT = "user_no_want"        # 用户明确不想说
    NATURAL_CLOSE = "natural_close"      # 自然收束


class QuoteOut(CamelModel):
    id: str
    content: str


class MessageOut(CamelModel):
    seq: int
    role: str
    content: str
    created_at: str


class SessionOut(CamelModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "sessionId": "01993f7b-8c1a-7de2-9f3a-1b2c3d4e5f60",
                    "status": "OPEN_CHAT",
                    "messages": [
                        {"seq": 1, "role": "guide", "content": "最近，有什么事一直挂在心上吗？"},
                        {"seq": 2, "role": "user",  "content": "最近有点迷茫，不知道下一步该往哪走。"},
                    ],
                    "quote": None,
                },
                {
                    "sessionId": "01993f81-2b3c-7d4e-8f5a-6b7c8d9e0f1a",
                    "status": "COMPLETED",
                    "messages": [],
                    "quote": {
                        "id": "01993f81-2b3c-7d4e-8f5a-6b7c8d9e0f1b",
                        "content": "不必今天就把整条路看清。先走到下一盏灯下，再决定往哪里去。",
                    },
                },
            ]
        },
    )

    session_id: str
    status: SessionStatus
    end_kind: EndKind | None = None
    messages: list[MessageOut] = []
    quote: QuoteOut | None = None


class MessageIn(CamelModel):
    """用户消息。开放式聊天，永远是 free text，不带 round 概念。"""

    content: str = Field(min_length=1, max_length=2000)


class SubmitMessageRequest(CamelModel):
    message: MessageIn


class EndRequest(CamelModel):
    end_kind: EndKind


class CreateSessionRequest(CamelModel):
    pass


class RetryRequest(CamelModel):
    pass


# 兼容旧 API：保留 AnswerIn 形状但只接 content；新代码请用 MessageIn
class AnswerIn(CamelModel):
    type: Literal["text"] = "text"
    option_key: str | None = None
    content: str = Field(min_length=1, max_length=2000)
