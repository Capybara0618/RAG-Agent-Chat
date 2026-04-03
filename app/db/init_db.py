from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from app.models.base import Base


def init_db(session_factory: sessionmaker) -> None:
    engine = session_factory.kw["bind"]
    Base.metadata.create_all(bind=engine)