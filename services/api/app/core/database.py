"""Database Engine and Session Management

Uses SQLAlchemy 2.x with Psycopg 3.
Provides connection pooling, lifecycle management, and transactional session dependencies.
"""

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from app.core.logging import logger

# Configure database engine with connection pooling suitable for Supabase Transaction Pooler & Lambda
# Prepared statements are disabled (prepare_threshold: None) for PgBouncer transaction pooling
connect_args: dict[str, Any] = {}
if "sqlite" in settings.DATABASE_URL:
    connect_args = {"check_same_thread": False}
else:
    sslmode = (
        "require"
        if settings.ENVIRONMENT in ("production", "staging")
        or "supabase" in settings.DATABASE_URL
        or "pooler" in settings.DATABASE_URL
        else "prefer"
    )
    connect_args = {
        "sslmode": sslmode,
        "prepare_threshold": None,
    }

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE if "sqlite" not in settings.DATABASE_URL else 5,
    max_overflow=settings.DB_MAX_OVERFLOW if "sqlite" not in settings.DATABASE_URL else 10,
    pool_recycle=settings.DB_POOL_RECYCLE,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a transactional database session per request.

    Automatically rolls back on uncaught exception and closes session upon completion.
    """
    db: Session = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.error(f"Database session rolled back due to error: {e}")
        raise
    finally:
        db.close()
