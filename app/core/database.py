"""SQLAlchemy engine, session factory and table creation.

Tables are created via Base.metadata.create_all() instead of a migrations tool
(e.g. Alembic) — see README for the reasoning behind this choice.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Session:
    """FastAPI dependency that yields a DB session and always closes it after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables registered on Base.metadata.

    Must be called via a normal import (e.g. from main.py's startup, or
    `python -c "from app.core.database import init_db; init_db()"`), never by
    running this file with `python -m app.core.database` — that executes this
    module as __main__ instead of as app.core.database, so the deferred model
    import below ends up loading a *second* copy of this module (with its own,
    empty Base.metadata) and create_all() silently does nothing.
    """
    from app.models import produto  # noqa: F401 - registers Produto on Base.metadata

    Base.metadata.create_all(bind=engine)
