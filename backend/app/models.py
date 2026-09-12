"""ORM 模型：Session、Message、Quote 三张业务表。

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
    # 用户如何收束本次相遇：user_active / user_still_talking / user_no_want / natural_close
    end_kind: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class Message(Base):
    """用户说的话（或向导的固定回复，role 区分）。
    开放式聊天，没有固定轮次，seq 是会话内的递增序号。
    """

    __tablename__ = "message"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_message_session_seq"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user' | 'guide'
    content: Mapped[str] = mapped_column(nullable=False)
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
