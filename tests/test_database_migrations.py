from sqlalchemy import create_engine, inspect, text

from app.database import Base, _apply_schema_compatibility_migrations


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
