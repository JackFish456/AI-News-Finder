from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from news_agent.storage.orm import Base


def _ensure_sqlite_parent_dir(database_url: str) -> None:
    if database_url.startswith("sqlite:///"):
        path_part = database_url.removeprefix("sqlite:///")
        if path_part and not path_part.startswith(":memory:"):
            p = Path(path_part)
            if not p.is_absolute():
                p = Path.cwd() / p
            p.parent.mkdir(parents=True, exist_ok=True)


def get_engine(database_url: str):
    _ensure_sqlite_parent_dir(database_url)
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(database_url, echo=False, future=True, connect_args=connect_args)


def init_db(engine) -> None:
    Base.metadata.create_all(engine)


def get_session_factory(engine):
    return sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False, future=True)
