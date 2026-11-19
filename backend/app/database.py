import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.engine import Engine

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


def create_database_engine() -> Engine | None:
    """Create the SQLAlchemy engine when a database URL is configured."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None

    return create_engine(database_url, pool_pre_ping=True)


engine = create_database_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def get_db():
    """Yield a database session for a request."""
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured")

    db = SessionLocal(bind=engine)
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> None:
    """Raise an exception unless PostgreSQL responds to a simple query."""
    if engine is None:
        raise RuntimeError("DATABASE_URL is not configured")

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
