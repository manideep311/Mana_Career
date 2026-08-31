BASE = "/api/v1/profile"


async def _auth(client, email="prof@example.com"):
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-passphrase", "full_name": "Prof"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_get_profile_autocreates_and_returns_full_shape(client):
    h = await _auth(client)
    r = await client.get(BASE, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["profile_strength"] == 0
    assert body["experiences"] == [] and body["education"] == []


async def test_get_profile_requires_auth(client):
    assert (await client.get(BASE)).status_code == 401


async def test_put_profile_updates_and_rescores(client):
    h = await _auth(client, "put@example.com")
    r = await client.put(
        BASE, headers=h,
        json={"location": "Hyderabad", "career_goals": "Ship models."},
    )
    assert r.status_code == 200
    assert r.json()["profile_strength"] == 18
    assert r.json()["completeness"]["location"] is True


async def test_put_profile_rejects_unknown_field(client):
    h = await _auth(client, "unk@example.com")
    r = await client.put(BASE, headers=h, json={"nickname": "Neo"})
    assert r.status_code == 422


async def test_strength_endpoint_lists_missing(client):
    h = await _auth(client, "str@example.com")
    r = await client.get(f"{BASE}/strength", headers=h)
    assert r.status_code == 200
    assert r.json()["score"] == 0
    assert "Add your work experience" in r.json()["missing"]
