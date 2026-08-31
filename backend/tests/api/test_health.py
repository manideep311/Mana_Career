async def test_health_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_health_sets_request_id_header(client):
    r = await client.get("/health")
    assert r.headers.get("x-request-id")


async def test_health_echoes_incoming_request_id(client):
    r = await client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"


async def test_ready_reports_checks(client):
    r = await client.get("/health/ready")
    assert r.status_code in (200, 503)
    body = r.json()
    assert set(body["checks"]) == {"database", "redis", "migrations"}


async def test_unknown_route_is_problem_json(client):
    r = await client.get("/health/does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"
    assert r.json()["code"] == "not_found"
