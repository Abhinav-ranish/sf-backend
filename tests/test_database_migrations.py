from sqlalchemy import create_engine, inspect, text

from app.database import Base, _apply_schema_compatibility_migrations, _engine_url, _sqlite_memory_uri


def test_plain_memory_sqlite_uses_shared_memory_url():
    url = _engine_url("sqlite+pysqlite:///:memory:")

    assert url.startswith("sqlite+pysqlite:///file:contacts_api_memory?")
    assert "cache=shared" in url
    assert "mode=memory" in url
    assert "uri=true" in url
    keeper_uri = _sqlite_memory_uri(url)
    assert keeper_uri is not None
    assert keeper_uri.startswith("file:contacts_api_memory?")
    assert "cache=shared" in keeper_uri
    assert "mode=memory" in keeper_uri
    assert "uri=true" not in keeper_uri


def test_plain_memory_sqlite_preserves_query_options():
    url = _engine_url("sqlite+pysqlite:///:memory:?timeout=30")

    assert "file:contacts_api_memory" in url
    assert "cache=shared" in url
    assert "mode=memory" in url
    assert "timeout=30" in url
    assert "uri=true" in url


def test_custom_sqlite_memory_url_gets_keeper_uri():
    url = "sqlite+pysqlite:///file:custom_contacts?mode=memory&cache=shared&uri=true"

    assert _engine_url(url) == url
    assert _sqlite_memory_uri(url) == "file:custom_contacts?mode=memory&cache=shared"


def test_sqlite_filename_containing_memory_is_not_rewritten():
    url = "sqlite+pysqlite:///./contacts:memory:.db"

    assert _engine_url(url) == url
    assert _sqlite_memory_uri(url) is None


def test_compatibility_migration_adds_photo_and_backfills_addresses(tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'contacts.db'}"
    migration_engine = create_engine(db_url)

    with migration_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE contacts (
                    id INTEGER PRIMARY KEY,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    email VARCHAR(320) NOT NULL UNIQUE,
                    phone VARCHAR(40),
                    company VARCHAR(200),
                    job_title VARCHAR(200),
                    address VARCHAR(300),
                    city VARCHAR(120),
                    state VARCHAR(120),
                    postal_code VARCHAR(20),
                    country VARCHAR(120),
                    notes TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO contacts (
                    id, first_name, last_name, email, address, city, state,
                    postal_code, country, created_at, updated_at
                )
                VALUES (
                    1, 'Ada', 'Lovelace', 'ada@example.com', '1 Market St',
                    'San Francisco', 'CA', '94105', 'USA',
                    '2026-08-19T16:22:58', '2026-08-19T16:22:58'
                )
                """
            )
        )

    Base.metadata.create_all(bind=migration_engine)
    _apply_schema_compatibility_migrations(migration_engine)

    columns = {column["name"] for column in inspect(migration_engine).get_columns("contacts")}
    assert "photo" in columns

    with migration_engine.connect() as connection:
        address = connection.execute(text("SELECT * FROM contact_addresses")).mappings().one()

    assert address["contact_id"] == 1
    assert address["type"] == "Home"
    assert address["address"] == "1 Market St"
    assert address["city"] == "San Francisco"


def test_compatibility_migration_backfills_legacy_address_with_existing_addresses(tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'contacts.db'}"
    migration_engine = create_engine(db_url)

    with migration_engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE contacts (
                    id INTEGER PRIMARY KEY,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    email VARCHAR(320) NOT NULL UNIQUE,
                    phone VARCHAR(40),
                    company VARCHAR(200),
                    job_title VARCHAR(200),
                    address VARCHAR(300),
                    city VARCHAR(120),
                    state VARCHAR(120),
                    postal_code VARCHAR(20),
                    country VARCHAR(120),
                    notes TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO contacts (
                    id, first_name, last_name, email, address, city, state,
                    postal_code, country, created_at, updated_at
                )
                VALUES (
                    1, 'Ada', 'Lovelace', 'ada@example.com', '1 Market St',
                    'San Francisco', 'CA', '94105', 'USA',
                    '2026-08-19T16:22:58', '2026-08-19T16:22:58'
                )
                """
            )
        )

    Base.metadata.create_all(bind=migration_engine)

    with migration_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO contact_addresses (
                    contact_id, type, address, city, state, postal_code, country
                )
                VALUES (
                    1, 'Work', '88 Colin P Kelly Jr St',
                    'San Francisco', 'CA', '94107', 'USA'
                )
                """
            )
        )

    _apply_schema_compatibility_migrations(migration_engine)
    _apply_schema_compatibility_migrations(migration_engine)

    with migration_engine.connect() as connection:
        addresses = connection.execute(
            text("SELECT type, address, city, postal_code FROM contact_addresses ORDER BY id")
        ).mappings().all()

    assert [address["type"] for address in addresses] == ["Work", "Home"]
    assert addresses[0]["address"] == "88 Colin P Kelly Jr St"
    assert addresses[1]["address"] == "1 Market St"
    assert addresses[1]["postal_code"] == "94105"
