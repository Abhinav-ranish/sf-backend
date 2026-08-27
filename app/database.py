from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _engine_kwargs(database_url: str) -> dict:
    if not database_url.startswith("sqlite"):
        return {}

    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in database_url or "mode=memory" in database_url:
        # A plain in-memory SQLite database lives and dies with its connection.
        # StaticPool keeps a single connection alive so every request — and every
        # thread FastAPI hands work to — sees the same data for the process's lifetime.
        kwargs["poolclass"] = StaticPool
    return kwargs


settings = get_settings()

engine = create_engine(
    settings.database_url,
    echo=settings.sql_echo,
    **_engine_kwargs(settings.database_url),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _apply_schema_compatibility_migrations(bind: Engine) -> None:
    """Small upgrades for demo installs that already have a persisted schema."""
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "contacts" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("contacts")}
    if "photo" not in columns:
        with bind.begin() as connection:
            connection.execute(text("ALTER TABLE contacts ADD COLUMN photo TEXT"))
        columns.add("photo")

    legacy_address_columns = {"address", "city", "state", "postal_code", "country"}
    if "contact_addresses" not in tables or not legacy_address_columns.issubset(columns):
        return

    has_legacy_address = " OR ".join(
        f"TRIM(COALESCE({column}, '')) <> ''" for column in sorted(legacy_address_columns)
    )
    with bind.begin() as connection:
        connection.execute(
            text(
                f"""
                INSERT INTO contact_addresses
                    (contact_id, type, address, city, state, postal_code, country)
                SELECT
                    contacts.id, 'Home', contacts.address, contacts.city,
                    contacts.state, contacts.postal_code, contacts.country
                FROM contacts
                WHERE ({has_legacy_address})
                  AND NOT EXISTS (
                      SELECT 1
                      FROM contact_addresses
                      WHERE contact_addresses.contact_id = contacts.id
                  )
                """
            )
        )


def init_db() -> None:
    """Create and lightly upgrade tables. Called on startup; safe to call repeatedly."""
    from app import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _apply_schema_compatibility_migrations(engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
