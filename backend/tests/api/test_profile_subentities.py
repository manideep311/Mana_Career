import pytest

REG = "/api/v1/auth/register"


async def _auth(client, email):
    r = await client.post(
        REG, json={"email": email, "password": "correct-passphrase", "full_name": "X"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.parametrize(
    ("section", "create", "patch"),
    [
        ("experiences", {"company": "Acme", "title": "Eng"}, {"title": "Senior Eng"}),
        ("education", {"institution": "Uni"}, {"degree": "BSc"}),
        ("projects", {"name": "RAG"}, {"url": "https://x.dev"}),
        ("certifications", {"name": "AWS SAA"}, {"issuer": "AWS"}),
    ],
)
async def test_subentity_full_crud(client, section, create, patch):
    h = await _auth(client, f"{section}@example.com")
    base = f"/api/v1/profile/{section}"

    empty = await client.get(base, headers=h)
    assert empty.status_code == 200 and empty.json() == []

    created = await client.post(base, headers=h, json=create)
    assert created.status_code == 201
    item_id = created.json()["id"]
    assert created.json()["order_index"] == 0 and created.json()["source"] == "user"

    patched = await client.patch(f"{base}/{item_id}", headers=h, json=patch)
    assert patched.status_code == 200
    key, val = next(iter(patch.items()))
    assert patched.json()[key] == val

    listed = await client.get(base, headers=h)
    assert len(listed.json()) == 1

    deleted = await client.delete(f"{base}/{item_id}", headers=h)
    assert deleted.status_code == 204
    assert (await client.get(base, headers=h)).json() == []


async def test_subentity_reorder(client):
    h = await _auth(client, "reorder@example.com")
    base = "/api/v1/profile/education"
    a = (await client.post(base, headers=h, json={"institution": "A"})).json()["id"]
    b = (await client.post(base, headers=h, json={"institution": "B"})).json()["id"]
    r = await client.post(f"{base}/reorder", headers=h, json={"ids": [b, a]})
    assert r.status_code == 200
    assert [row["institution"] for row in r.json()] == ["B", "A"]


async def test_subentity_patch_rejects_unknown_field(client):
    h = await _auth(client, "pu@example.com")
    base = "/api/v1/profile/projects"
    pid = (await client.post(base, headers=h, json={"name": "P"})).json()["id"]
    r = await client.patch(f"{base}/{pid}", headers=h, json={"bogus": 1})
    assert r.status_code == 422


async def test_subentity_cross_user_returns_404(client):
    h1 = await _auth(client, "u1@example.com")
    h2 = await _auth(client, "u2@example.com")
    base = "/api/v1/profile/projects"
    pid = (await client.post(base, headers=h1, json={"name": "Mine"})).json()["id"]
    assert (await client.patch(f"{base}/{pid}", headers=h2, json={"name": "x"})).status_code == 404
    assert (await client.delete(f"{base}/{pid}", headers=h2)).status_code == 404


async def test_creating_experience_bumps_strength(client):
    h = await _auth(client, "bump@example.com")
    await client.post("/api/v1/profile/experiences", headers=h,
                      json={"company": "Acme", "title": "Eng"})
    prof = await client.get("/api/v1/profile", headers=h)
    assert prof.json()["profile_strength"] == 16  # work experience weight
