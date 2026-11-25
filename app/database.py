from typing import Generator
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine
from app.config import get_settings

settings = get_settings()

# Engine configuration
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
        "timeout": 30.0,
    }

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=connect_args,
)


@event.listens_for(engine, "connect")
def configure_sqlite_pragmas(dbapi_connection, connection_record):
    """
    Configure SQLite pragmas for foreign key support, WAL mode concurrency,
    and busy timeouts.
    """
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=30000;")
        # Avoid setting WAL on pure in-memory SQLite databases (:memory:)
        if ":memory:" not in settings.DATABASE_URL:
            cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.close()


def init_db() -> None:
    """
    Initialize database tables for registered SQLModel metadata.
    NOTE: SQLModel.metadata.create_all() creates missing tables only.
    It does not perform database schema migrations (for schema changes in
    production, a migration tool such as Alembic is recommended).
    """
    # Import all models to ensure they are registered with SQLModel metadata
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a request-scoped database session.
    """
    with Session(engine) as session:
        yield session
