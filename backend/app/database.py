"""数据库引擎与会话工厂。本地默认 SQLite，通过 DATABASE_URL 可切换 PostgreSQL。"""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base


def create_engine_from_url(url: str) -> Engine:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        # timeout：SQLite 写锁的忙等待秒数，多用户演示时避免立刻报 database is locked
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if _is_memory_sqlite(url):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite") and not _is_memory_sqlite(url):
        _enable_sqlite_wal(engine)
    return engine


def _enable_sqlite_wal(engine: Engine) -> None:
    """WAL 模式允许读写并发，显著降低演示期间的锁冲突。"""
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def _is_memory_sqlite(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or url.startswith("sqlite:///:memory:")


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _ensure_columns(engine)


def _ensure_columns(engine: Engine) -> None:
    """无迁移工具的轻量列补齐，让旧开发库也能启动（Demo 数据可随时删除重建）。"""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    additions = {
        "session": {"active_question_key": "VARCHAR(64)"},
        "answer": {"question_key": "VARCHAR(64)"},
    }
    with engine.begin() as conn:
        for table, columns in additions.items():
            if table not in tables:
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for column, ddl in columns.items():
                if column not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def new_db_session(factory: sessionmaker) -> OrmSession:
    return factory()
