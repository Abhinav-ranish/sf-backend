import base64

from PIL import Image

from app.schemas import MAX_PHOTO_BYTES

BASE = "/api/v1/contacts"
SMALL_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
)
SMALL_PHOTO = f"data:image/png;base64,{SMALL_PNG}"
WORK_ADDRESS = {
    "type": "Work",
    "address": "88 Colin P Kelly Jr St",
    "city": "San Francisco",
    "state": "CA",
    "postal_code": "94107",
    "country": "USA",
}


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "sqlite"


def test_create_contact(client, payload):
    response = client.post(BASE, json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["email"] == "ada@example.com"
    assert body["full_name"] == "Ada Lovelace"
    assert body["photo"] is None
    assert body["addresses"][0]["type"] == "Home"
    assert body["addresses"][0]["id"] > 0
    assert body["created_at"] and body["updated_at"]


def test_create_stores_photo_and_multiple_addresses(client, payload):
    response = client.post(
        BASE,
        json={**payload, "photo": SMALL_PHOTO, "addresses": [payload["addresses"][0], WORK_ADDRESS]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["photo"] == SMALL_PHOTO
    assert [address["type"] for address in body["addresses"]] == ["Home", "Work"]
    assert body["addresses"][1]["address"] == "88 Colin P Kelly Jr St"


def test_create_rejects_unsupported_photo_type(client, payload):
    response = client.post(BASE, json={**payload, "photo": "data:image/gif;base64,R0lGODdh"})
    assert response.status_code == 422


def test_create_rejects_non_image_photo_bytes(client, payload):
    non_image = base64.b64encode(b"avatar").decode()
    response = client.post(BASE, json={**payload, "photo": f"data:image/png;base64,{non_image}"})
    assert response.status_code == 422


def test_create_rejects_photo_mime_mismatch(client, payload):
    response = client.post(BASE, json={**payload, "photo": f"data:image/jpeg;base64,{SMALL_PNG}"})
    assert response.status_code == 422


def test_create_rejects_oversized_photo(client, payload):
    oversized = base64.b64encode(b"x" * (MAX_PHOTO_BYTES + 1)).decode()
    response = client.post(BASE, json={**payload, "photo": f"data:image/jpeg;base64,{oversized}"})
    assert response.status_code == 422


def test_create_rejects_decompression_bomb_photo(client, payload, monkeypatch):
    def raise_bomb(*_args, **_kwargs):
        raise Image.DecompressionBombError("image is too large")

    monkeypatch.setattr("app.schemas.Image.open", raise_bomb)

    response = client.post(BASE, json={**payload, "photo": SMALL_PHOTO})
    assert response.status_code == 422


def test_create_rejects_blank_address_item(client, payload):
    response = client.post(BASE, json={**payload, "addresses": [{"type": "Other"}]})
    assert response.status_code == 422

    response = client.post(BASE, json={**payload, "addresses": [{"type": "Other", "address": "   "}]})
    assert response.status_code == 422


def test_create_rejects_legacy_flat_address_fields(client, payload):
    response = client.post(BASE, json={**payload, "address": "1 Old Way", "city": "San Francisco"})
    assert response.status_code == 422


def test_patch_rejects_legacy_flat_address_fields(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"address": "1 Old Way"})
    assert response.status_code == 422


def test_create_requires_valid_email(client, payload):
    response = client.post(BASE, json={**payload, "email": "not-an-email"})
    assert response.status_code == 422


def test_create_requires_names(client, payload):
    response = client.post(BASE, json={**payload, "first_name": ""})
    assert response.status_code == 422


def test_duplicate_email_conflicts(client, payload):
    assert client.post(BASE, json=payload).status_code == 201
    response = client.post(BASE, json={**payload, "email": "ADA@example.com"})
    assert response.status_code == 409


def test_get_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.get(f"{BASE}/{contact_id}")
    assert response.status_code == 200
    assert response.json()["id"] == contact_id


def test_get_missing_contact_returns_404(client):
    assert client.get(f"{BASE}/9999").status_code == 404


def test_list_pagination_and_total(client, payload):
    for index in range(5):
        client.post(BASE, json={**payload, "email": f"user{index}@example.com"})

    response = client.get(BASE, params={"limit": 2, "offset": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2 and body["offset"] == 2


def test_list_returns_lightweight_items(client, payload):
    client.post(BASE, json={**payload, "photo": SMALL_PHOTO, "notes": "private"})

    response = client.get(BASE)

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["full_name"] == "Ada Lovelace"
    assert "photo" not in item
    assert "addresses" not in item
    assert "notes" not in item


def test_list_search(client, payload):
    client.post(BASE, json=payload)
    client.post(
        BASE,
        json={**payload, "first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com", "company": "US Navy"},
    )

    hits = client.get(BASE, params={"search": "hopper"}).json()
    assert hits["total"] == 1
    assert hits["items"][0]["last_name"] == "Hopper"

    by_company = client.get(BASE, params={"search": "navy"}).json()
    assert by_company["total"] == 1

    misses = client.get(BASE, params={"search": "nobody"}).json()
    assert misses["total"] == 0


def test_list_sorting(client, payload):
    client.post(BASE, json={**payload, "last_name": "Zhang", "email": "z@example.com"})
    client.post(BASE, json={**payload, "last_name": "Adams", "email": "a@example.com"})

    names = [
        item["last_name"]
        for item in client.get(BASE, params={"sort_by": "last_name", "order": "asc"}).json()["items"]
    ]
    assert names == ["Adams", "Zhang"]


def test_list_rejects_bad_sort_field(client):
    assert client.get(BASE, params={"sort_by": "; DROP TABLE contacts"}).status_code == 422


def test_patch_updates_only_sent_fields(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"phone": "+1-000-000-0000"})
    assert response.status_code == 200
    body = response.json()
    assert body["phone"] == "+1-000-000-0000"
    assert body["first_name"] == "Ada"
    assert body["company"] == "Analytical Engines"
    assert body["addresses"][0]["city"] == "San Francisco"


def test_patch_can_replace_or_clear_addresses(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]

    response = client.patch(f"{BASE}/{contact_id}", json={"addresses": [WORK_ADDRESS]})
    assert response.status_code == 200
    body = response.json()
    assert len(body["addresses"]) == 1
    assert body["addresses"][0]["type"] == "Work"

    response = client.patch(f"{BASE}/{contact_id}", json={"addresses": None})
    assert response.status_code == 200
    assert response.json()["addresses"] == []


def test_patch_can_update_or_clear_photo(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]

    response = client.patch(f"{BASE}/{contact_id}", json={"photo": SMALL_PHOTO})
    assert response.status_code == 200
    assert response.json()["photo"] == SMALL_PHOTO

    response = client.patch(f"{BASE}/{contact_id}", json={"photo": None})
    assert response.status_code == 200
    assert response.json()["photo"] is None


def test_patch_duplicate_email_conflicts(client, payload):
    first = client.post(BASE, json=payload).json()["id"]
    client.post(BASE, json={**payload, "email": "grace@example.com"})
    response = client.patch(f"{BASE}/{first}", json={"email": "grace@example.com"})
    assert response.status_code == 409


def test_patch_same_email_is_allowed(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.patch(f"{BASE}/{contact_id}", json={"email": payload["email"]})
    assert response.status_code == 200


def test_put_replaces_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    response = client.put(
        f"{BASE}/{contact_id}",
        json={"first_name": "Grace", "last_name": "Hopper", "email": "grace@example.com"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Grace Hopper"
    assert body["company"] is None  # omitted fields are cleared by PUT
    assert body["photo"] is None
    assert body["addresses"] == []


def test_put_preserves_photo_when_sent_and_replaces_addresses(client, payload):
    contact_id = client.post(BASE, json={**payload, "photo": SMALL_PHOTO}).json()["id"]
    response = client.put(
        f"{BASE}/{contact_id}",
        json={
            **payload,
            "last_name": "Byron",
            "photo": SMALL_PHOTO,
            "addresses": [payload["addresses"][0], WORK_ADDRESS],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Ada Byron"
    assert body["photo"] == SMALL_PHOTO
    assert [address["type"] for address in body["addresses"]] == ["Home", "Work"]


def test_put_missing_contact_returns_404(client):
    response = client.put(
        f"{BASE}/9999",
        json={"first_name": "A", "last_name": "B", "email": "ab@example.com"},
    )
    assert response.status_code == 404


def test_delete_contact(client, payload):
    contact_id = client.post(BASE, json=payload).json()["id"]
    assert client.delete(f"{BASE}/{contact_id}").status_code == 204
    assert client.get(f"{BASE}/{contact_id}").status_code == 404
    assert client.delete(f"{BASE}/{contact_id}").status_code == 404


def test_root_lists_entrypoints(client):
    body = client.get("/").json()
    assert body["contacts"] == BASE
