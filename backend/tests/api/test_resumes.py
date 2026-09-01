import io

from pypdf import PdfWriter


def _pdf(pages=1, text_pages=0) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=300, height=300)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


async def _auth(client, email="res@example.com"):
    r = await client.post("/api/v1/auth/register",
                          json={"email": email, "password": "correct-passphrase",
                                "full_name": "Res"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_upload_returns_202_and_lists(client):
    h = await _auth(client)
    up = await client.post("/api/v1/resumes", headers=h,
                           files={"file": ("cv.pdf", _pdf(), "application/pdf")})
    assert up.status_code == 202
    body = up.json()
    assert body["status"] == "uploaded" and body["is_primary"] is True
    lst = await client.get("/api/v1/resumes", headers=h)
    assert [r["id"] for r in lst.json()] == [body["id"]]


async def test_upload_rejects_non_pdf(client):
    h = await _auth(client, "npdf@example.com")
    r = await client.post("/api/v1/resumes", headers=h,
                          files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 422 and r.json()["code"] == "resume.not_pdf"


async def test_extraction_404_until_extracted(client):
    h = await _auth(client, "ex@example.com")
    up = await client.post("/api/v1/resumes", headers=h,
                           files={"file": ("cv.pdf", _pdf(), "application/pdf")})
    rid = up.json()["id"]
    r = await client.get(f"/api/v1/resumes/{rid}/extraction", headers=h)
    assert r.status_code == 404 and r.json()["code"] == "resume.not_extracted"


async def test_resume_is_user_scoped(client):
    h1 = await _auth(client, "o1@example.com")
    h2 = await _auth(client, "o2@example.com")
    rid = (await client.post("/api/v1/resumes", headers=h1,
                             files={"file": ("cv.pdf", _pdf(), "application/pdf")})).json()["id"]
    assert (await client.get(f"/api/v1/resumes/{rid}", headers=h2)).status_code == 404
    assert (await client.delete(f"/api/v1/resumes/{rid}", headers=h2)).status_code == 404
