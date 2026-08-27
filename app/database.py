import sqlite3
from collections.abc import Generator
from urllib.parse import urlencode

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_SHARED_MEMORY_URI = "file:contacts_api_memory?mode=memory&cache=shared"


def _is_sqlite_memory_url(database_url: str) -> bool:
    return database_url.startswith("sqlite") and (
        ":memory:" in database_url or "mode=memory" in database_url
    )


def _engine_url(database_url: str) -> str:
    if database_url.startswith("sqlite") and ":memory:" in database_url:
        prefix = database_url.rsplit(":memory:", 1)[0]
        return f"{prefix}{_SHARED_MEMORY_URI}&uri=true"
    return database_url


def _sqlite_memory_uri(database_url: str) -> str | None:
    if not _is_sqlite_memory_url(database_url):
        return None

    url = make_url(database_url)
    database = (url.database or "").lstrip("/")
    if database == ":memory:":
        return _SHARED_MEMORY_URI

    query = dict(url.query)
    query.pop("uri", None)
    query_string = urlencode(query, doseq=True)
    return f"{database}?{query_string}" if query_string else database


def _engine_kwargs(database_url: str) -> dict:
    if not database_url.startswith("sqlite"):
        return {}

    # SQLite connections are thread-bound by default. FastAPI can serve sync
    # endpoints on worker threads, so allow SQLite connections across them —
    # and hand every request a fresh connection (NullPool) so no two requests
    # ever share one. The shared-cache URI keeps them on the same database.
    return {"connect_args": {"check_same_thread": False}, "poolclass": NullPool}


settings = get_settings()
database_url = _engine_url(settings.database_url)

engine = create_engine(
    database_url,
    echo=settings.sql_echo,
    **_engine_kwargs(database_url),
)

# A shared-cache in-memory database is dropped the moment its last connection
# closes. Pin one connection open for the process lifetime so the data
# survives pool churn between requests.
_memory_keeper = (
    sqlite3.connect(memory_uri, uri=True, check_same_thread=False)
    if (memory_uri := _sqlite_memory_uri(database_url)) is not None
    else None
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
                        AND contact_addresses.type = 'Home'
                        AND COALESCE(contact_addresses.address, '') = COALESCE(contacts.address, '')
                        AND COALESCE(contact_addresses.city, '') = COALESCE(contacts.city, '')
                        AND COALESCE(contact_addresses.state, '') = COALESCE(contacts.state, '')
                        AND COALESCE(contact_addresses.postal_code, '') = COALESCE(contacts.postal_code, '')
                        AND COALESCE(contact_addresses.country, '') = COALESCE(contacts.country, '')
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
