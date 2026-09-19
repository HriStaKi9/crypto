"""Database engine/session helper, ползван от всички ingestion модули.

Чете DATABASE_URL от средата (.env, зареден през python-dotenv).
db/schema.sql е единственият източник на истина за структурата — тук
не дублираме таблиците като ORM модели, само connection layer.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL не е зададен — копирай .env.example на .env и го попълни."
        )
    return create_engine(url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), future=True, expire_on_commit=False)


@contextmanager
def get_session() -> Iterator[Session]:
    """Session за един ingestion run. Rollback автоматично при грешка."""
    session = _session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
