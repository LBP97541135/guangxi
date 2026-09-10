"""前后端联调契约：会话状态、请求/响应 Schema。字段以 camelCase 输出。"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SessionStatus(str, Enum):
    QUESTION_1 = "QUESTION_1"
    QUESTION_2 = "QUESTION_2"
    QUESTION_3 = "QUESTION_3"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


AnswerType = Literal["option", "text"]


class OptionOut(CamelModel):
    key: str
    label: str


class QuestionOut(CamelModel):
    key: str
    title: str | None = None
    text: str
    options: list[OptionOut]
    allow_free_text: bool
    scene_example: str | None = None


class QuoteOut(CamelModel):
    id: str
    content: str


class SessionOut(CamelModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "sessionId": "01993f7b-8c1a-7de2-9f3a-1b2c3d4e5f60",
                    "status": "QUESTION_1",
                    "currentRound": 1,
                    "question": {
                        "key": "surface_scene",
                        "text": "最近有没有一个瞬间，让你突然觉得自己不像平时的自己？",
                        "options": [{"key": "alone", "label": "一个人时"}],
                        "allowFreeText": True,
                    },
                    "quote": None,
                },
                {
                    "sessionId": "01993f80-1a2b-7c3d-9e4f-5a6b7c8d9e0f",
                    "status": "COMPLETED",
                    "currentRound": 3,
                    "question": None,
                    "quote": {
                        "id": "01993f81-2b3c-7d4e-8f5a-6b7c8d9e0f1a",
                        "content": "其实，你不是习惯沉默，只是总把自己的风雨藏在别人屋檐之外。",
                    },
                },
            ]
        },
    )

    session_id: str
    status: SessionStatus
    current_round: int
    question: QuestionOut | None = None
    quote: QuoteOut | None = None


class AnswerIn(CamelModel):
    type: AnswerType
    option_key: str | None = None
    content: str | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> "AnswerIn":
        if self.type == "option":
            if not self.option_key:
                raise ValueError("快捷选项回答必须提供 optionKey")
            if self.content is not None:
                raise ValueError("快捷选项回答不应携带 content")
        else:
            if self.content is None or not self.content.strip():
                raise ValueError("自由文本回答必须提供非空 content")
            if self.option_key is not None:
                raise ValueError("自由文本回答不应携带 optionKey")
        return self


class SubmitAnswerRequest(CamelModel):
    round: int = Field(ge=1, le=3)
    answer: AnswerIn


class CreateSessionRequest(CamelModel):
    pass


class RetryRequest(CamelModel):
    pass
