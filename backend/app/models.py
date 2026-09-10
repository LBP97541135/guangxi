"""ORM 模型：Session、Answer、Quote 三张业务表。

不提前增加用户、分享、图鉴等字段。数据唯一性由数据库约束保证。
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import MetaData, String, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class QuoteStatus(str, Enum):
    GENERATING = "GENERATING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Session(Base):
    __tablename__ = "session"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    current_round: Mapped[int] = mapped_column(nullable=False)
    active_question_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class Answer(Base):
    __tablename__ = "answer"
    __table_args__ = (UniqueConstraint("session_id", "round_no", name="uq_answer_session_round"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    round_no: Mapped[int] = mapped_column(nullable=False)
    question_key: Mapped[str | None] = mapped_column(String(64))
    answer_type: Mapped[str] = mapped_column(String(20), nullable=False)
    option_key: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)


class Quote(Base):
    __tablename__ = "quote"
    __table_args__ = (UniqueConstraint("session_id", name="uq_quote_session"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content: Mapped[str | None]
    model: Mapped[str | None] = mapped_column(String(64))
    generation_attempts: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(
        SqlEnum(QuoteStatus, native_enum=False, length=20), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
