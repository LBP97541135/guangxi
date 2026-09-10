"""三问配置：格式定义、加载与启动校验。

配置文件为 config/questions.json。每一轮允许配置多道情境题（"换个情境"
在轮内切换），文案终稿由策划直接替换该文件。
非法配置在启动时被发现，而不是用户请求时才报错。
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class QuestionsConfigError(Exception):
    """questions.json 格式或内容非法。"""


class QuestionOptionDef(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)


class QuestionDef(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    round: int
    key: str = Field(min_length=1)
    title: str | None = None
    text: str = Field(min_length=1)
    options: list[QuestionOptionDef] = Field(default_factory=list)
    allow_free_text: bool = False
    scene_example: str | None = None

    @model_validator(mode="after")
    def _validate_answerable(self) -> "QuestionDef":
        if not self.options and not self.allow_free_text:
            raise ValueError(f"问题 {self.key} 至少需要快捷选项或 allowFreeText 之一")
        option_keys = [o.key for o in self.options]
        if len(option_keys) != len(set(option_keys)):
            raise ValueError(f"问题 {self.key} 的选项 Key 重复")
        return self


class QuestionsConfig(BaseModel):
    questions: list[QuestionDef]

    @model_validator(mode="after")
    def _validate_rounds(self) -> "QuestionsConfig":
        rounds = {q.round for q in self.questions}
        if rounds != {1, 2, 3}:
            raise ValueError(f"三轮配置必须覆盖轮次 1、2、3，实际为 {sorted(rounds)}")
        keys = [q.key for q in self.questions]
        if len(keys) != len(set(keys)):
            raise ValueError("问题 Key 重复")
        return self

    def variants_for_round(self, round_no: int) -> list[QuestionDef]:
        variants = [q for q in self.questions if q.round == round_no]
        if not variants:
            raise KeyError(f"配置中不存在轮次 {round_no}")
        return variants

    def default_for_round(self, round_no: int) -> QuestionDef:
        return self.variants_for_round(round_no)[0]

    def by_key(self, key: str) -> QuestionDef:
        for question in self.questions:
            if question.key == key:
                return question
        raise KeyError(f"配置中不存在问题 {key}")


def load_questions(path: Path) -> QuestionsConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return QuestionsConfig.model_validate(raw)
    except FileNotFoundError as exc:
        raise QuestionsConfigError(f"问题配置文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise QuestionsConfigError(f"问题配置不是合法 JSON: {path}: {exc}") from exc
    except ValueError as exc:
        raise QuestionsConfigError(f"问题配置非法: {exc}") from exc
