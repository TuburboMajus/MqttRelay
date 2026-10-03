# Database configuration and session management for SQLAlchemy
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import NullPool
from typing import Optional
import os

# SQLAlchemy declarative base for all models
Base = declarative_base()

# Global engine and session factory
_engine = None
_SessionLocal = None


def init_db(database_url: str, echo: bool = False):
    """
    Initialize database connection and session factory.
    
    Args:
        database_url: PostgreSQL connection string (e.g., postgresql://user:pass@host/db)
        echo: Whether to echo SQL statements (useful for debugging)
    """
    global _engine, _SessionLocal
    
    # Use NullPool to avoid connection pooling issues with concurrent processes
    _engine = create_engine(
        database_url,
        echo=echo,
        poolclass=NullPool,
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {}
    )
    
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    
    # Enable foreign keys for SQLite (if used for testing)
    if "sqlite" in database_url:
        @event.listens_for(_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()


def get_session() -> Session:
    """Get a new database session."""
    if _SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _SessionLocal()


def create_all_tables():
    """Create all database tables."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    Base.metadata.create_all(_engine)


def drop_all_tables():
    """Drop all database tables (DANGEROUS - for testing only)."""
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    Base.metadata.drop_all(_engine)
