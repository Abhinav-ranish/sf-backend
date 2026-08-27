# sf-backend

FastAPI contact-management API for the SF contacts challenge. It uses SQLAlchemy
with an in-memory SQLite database by default, seeds three sample contacts on
startup, and exposes interactive OpenAPI docs at `/docs`.

## Features

- CRUD endpoints for contacts.
- Search, sort, limit, and offset pagination for the contacts list.
- Optional contact photo stored as a JPEG, PNG, or WebP data URL.
- Lightweight list responses that omit full photo data.
- One-to-many contact addresses through a `contact_addresses` table.
- Address labels constrained to `Home`, `Work`, or `Other`.
- Lightweight startup compatibility migration for existing SQLite databases.

## Quick Start

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.main
```

Open these URLs after the server starts:

| URL | Purpose |
| --- | --- |
| <http://127.0.0.1:8000/docs> | Swagger UI |
| <http://127.0.0.1:8000/redoc> | ReDoc API reference |
| <http://127.0.0.1:8000/health> | Health check |
| <http://127.0.0.1:8000/api/v1/contacts> | Contacts collection |

The default database is in memory, so data is reset when the process exits. To
persist data locally:

```bash
CONTACTS_DATABASE_URL="sqlite+pysqlite:///./contacts.db" .venv/bin/python -m app.main
```

## Configuration

All settings are environment variables prefixed with `CONTACTS_`. A local `.env`
file is also read.

| Variable | Default | Purpose |
| --- | --- | --- |
| `CONTACTS_DATABASE_URL` | `sqlite+pysqlite:///:memory:` | SQLAlchemy database URL |
| `CONTACTS_SEED_DATA` | `true` | Seed sample contacts when the database is empty |
| `CONTACTS_HOST` | `127.0.0.1` | Server bind address |
| `CONTACTS_PORT` | `8000` | Server port |
| `CONTACTS_SQL_ECHO` | `false` | Log SQL statements |

## API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Liveness and database status |
| `GET` | `/` | API entry point |
| `GET` | `/api/v1/contacts` | List lightweight contact summaries |
| `POST` | `/api/v1/contacts` | Create a contact |
| `GET` | `/api/v1/contacts/{id}` | Fetch one contact |
| `PUT` | `/api/v1/contacts/{id}` | Replace one contact |
| `PATCH` | `/api/v1/contacts/{id}` | Partially update one contact |
| `DELETE` | `/api/v1/contacts/{id}` | Delete one contact |

List query parameters:

| Parameter | Default | Notes |
| --- | --- | --- |
| `search` | none | Case-insensitive match on name, email, company, or phone |
| `limit` | `50` | Between 1 and 200 |
| `offset` | `0` | Number of matching contacts to skip |
| `sort_by` | `id` | `id`, `first_name`, `last_name`, `email`, `company`, `created_at`, `updated_at` |
| `order` | `asc` | `asc` or `desc` |

## Contact Shape

`first_name`, `last_name`, and `email` are required. Email addresses are unique
case-insensitively and stored lowercased.

Optional contact fields:

- `phone`
- `photo`
- `company`
- `job_title`
- `addresses`
- `notes`

Create, get, replace, and update responses return the full contact, including
`photo`, `addresses`, and `notes`. The paginated list endpoint returns summary
items only, so large photo data URLs are not repeated across every row; fetch an
individual contact when the full payload is needed.

Unknown request fields are rejected with `422`, including the old flat
`address`, `city`, `state`, `postal_code`, and `country` fields. Send postal
data through `addresses` instead.

`photo` must be a data URL with MIME type `image/jpeg`, `image/png`, or
`image/webp`. The decoded image must be 512 KB or smaller.

`addresses` is an array with up to 10 items. Each address has a required `type`
of `Home`, `Work`, or `Other`, plus optional postal fields:

- `address`
- `city`
- `state`
- `postal_code`
- `country`

Each address item must include at least one postal field after trimming
whitespace. `PATCH` preserves existing addresses when `addresses` is omitted;
send `addresses: []` or `addresses: null` to clear them.

Example create payload:

```json
{
  "first_name": "Ada",
  "last_name": "Lovelace",
  "email": "ada@example.com",
  "phone": "+1-415-555-0101",
  "photo": null,
  "company": "Analytical Engines",
  "job_title": "Mathematician",
  "addresses": [
    {
      "type": "Home",
      "address": "1 Market St, Suite 400",
      "city": "San Francisco",
      "state": "CA",
      "postal_code": "94105",
      "country": "USA"
    },
    {
      "type": "Work",
      "address": "88 Colin P Kelly Jr St",
      "city": "San Francisco",
      "state": "CA",
      "postal_code": "94107",
      "country": "USA"
    }
  ],
  "notes": "Met at the SF hackathon."
}
```

## Database Notes

The current model has two tables:

- `contacts` stores identity, email, phone, photo, work fields, notes, and timestamps.
- `contact_addresses` stores typed postal addresses with a foreign key to `contacts`.

At startup, `init_db()` creates missing tables and applies a small compatibility
upgrade for existing SQLite databases: it adds the `contacts.photo` column when
missing and backfills old single-address columns into `contact_addresses` when
needed.

## Tests

```bash
.venv/bin/python -m pytest
```

Tests use their own in-memory database with seed data disabled.

## Project Layout

```text
app/
  main.py             FastAPI app, lifespan startup, /health, and /
  config.py           Environment-driven settings
  database.py         Engine, session factory, and startup compatibility migration
  models.py           Contact and ContactAddress ORM models
  schemas.py          Pydantic request and response models
  crud.py             Database operations
  seed.py             Sample contacts
  routers/contacts.py Contacts REST endpoints
tests/                API and migration tests
```
