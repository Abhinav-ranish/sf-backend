from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, load_only, selectinload

from app.models import Contact, ContactAddress
from app.schemas import ContactCreate, ContactReplace, ContactUpdate

SORTABLE_FIELDS = ("id", "first_name", "last_name", "email", "company", "created_at", "updated_at")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _address_models(addresses: list[dict] | None) -> list[ContactAddress]:
    return [ContactAddress(**address) for address in addresses or []]


def get_contact(db: Session, contact_id: int) -> Contact | None:
    stmt = select(Contact).options(selectinload(Contact.addresses)).where(Contact.id == contact_id)
    return db.execute(stmt).scalar_one_or_none()


def get_contact_by_email(db: Session, email: str) -> Contact | None:
    stmt = select(Contact).where(func.lower(Contact.email) == _normalize_email(email))
    return db.execute(stmt).scalar_one_or_none()


def count_contacts(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Contact)).scalar_one()


def list_contacts(
    db: Session,
    *,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "id",
    order: str = "asc",
) -> tuple[list[Contact], int]:
    """Return (page of contacts, total matching count)."""
    base_stmt = select(Contact)

    if search:
        pattern = f"%{search.strip().lower()}%"
        base_stmt = base_stmt.where(
            or_(
                func.lower(Contact.first_name).like(pattern),
                func.lower(Contact.last_name).like(pattern),
                func.lower(Contact.email).like(pattern),
                func.lower(func.coalesce(Contact.company, "")).like(pattern),
                func.lower(func.coalesce(Contact.phone, "")).like(pattern),
            )
        )

    total = db.execute(select(func.count()).select_from(base_stmt.subquery())).scalar_one()

    if sort_by not in SORTABLE_FIELDS:
        sort_by = "id"
    column = getattr(Contact, sort_by)
    stmt = base_stmt.options(
        load_only(
            Contact.id,
            Contact.first_name,
            Contact.last_name,
            Contact.email,
            Contact.phone,
            Contact.company,
            Contact.job_title,
            Contact.created_at,
            Contact.updated_at,
        )
    ).order_by(column.desc() if order == "desc" else column.asc())

    items = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return list(items), total


def create_contact(db: Session, payload: ContactCreate) -> Contact:
    data = payload.model_dump()
    addresses = data.pop("addresses", [])
    data["email"] = _normalize_email(data["email"])
    contact = Contact(**data, addresses=_address_models(addresses))
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def replace_contact(db: Session, contact: Contact, payload: ContactReplace) -> Contact:
    data = payload.model_dump()
    addresses = data.pop("addresses", [])
    for field, value in data.items():
        setattr(contact, field, _normalize_email(value) if field == "email" else value)
    contact.addresses = _address_models(addresses)
    db.commit()
    db.refresh(contact)
    return contact


def update_contact(db: Session, contact: Contact, payload: ContactUpdate) -> Contact:
    data = payload.model_dump(exclude_unset=True)
    missing = object()
    addresses = data.pop("addresses", missing)
    for field, value in data.items():
        setattr(contact, field, _normalize_email(value) if field == "email" else value)
    if addresses is not missing:
        contact.addresses = _address_models(addresses)
    db.commit()
    db.refresh(contact)
    return contact


def delete_contact(db: Session, contact: Contact) -> None:
    db.delete(contact)
    db.commit()
