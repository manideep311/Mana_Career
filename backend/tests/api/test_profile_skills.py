async def _auth(client, email="skapi@example.com"):
    r = await client.post("/api/v1/auth/register",
                          json={"email": email, "password": "correct-passphrase",
                                "full_name": "SK"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_strength_has_dimensions(client):
    h = await _auth(client)
    r = await client.get("/api/v1/profile/strength", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["dimensions"], list)
    assert sum(d["max"] for d in body["dimensions"]) == 100
    assert any(d["key"] == "skills_mapped" for d in body["dimensions"])


async def test_skills_empty_then_rebuild_202(client):
    h = await _auth(client, "skapi2@example.com")
    assert (await client.get("/api/v1/profile/skills", headers=h)).json() == []
    rb = await client.post("/api/v1/profile/rebuild", headers=h)
    assert rb.status_code == 202
