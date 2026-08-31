import datetime as dt
import uuid

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.auth import (
    MIN_PASSWORD_LENGTH,
    AuthResponse,
    RegisterIn,
    UserOut,
)


def test_register_in_rejects_short_password():
    with pytest.raises(ValidationError):
        RegisterIn(email="a@b.com", password="x" * (MIN_PASSWORD_LENGTH - 1), full_name="A")


def test_register_in_rejects_bad_email():
    with pytest.raises(ValidationError):
        RegisterIn(email="not-an-email", password="x" * MIN_PASSWORD_LENGTH, full_name="A")


def test_register_in_trims_full_name_and_email():
    m = RegisterIn(email="  a@b.com  ", password="x" * MIN_PASSWORD_LENGTH,
                   full_name="  A Person  ")
    assert m.full_name == "A Person"
    assert m.email == "a@b.com"


def test_register_in_rejects_blank_full_name():
    with pytest.raises(ValidationError):
        RegisterIn(email="a@b.com", password="x" * MIN_PASSWORD_LENGTH, full_name="   ")


def test_user_out_from_attributes():
    class _U:
        id = uuid.uuid4()
        email = "a@b.com"
        full_name = "A"
        is_admin = False
        created_at = dt.datetime.now(dt.UTC)

    out = UserOut.model_validate(_U())
    assert out.email == "a@b.com" and out.is_admin is False


def test_auth_response_defaults_token_type_bearer():
    r = AuthResponse(
        access_token="t", expires_in=900,
        user=UserOut(id=uuid.uuid4(), email="a@b.com", full_name="A",
                     is_admin=False, created_at=dt.datetime.now(dt.UTC)),
    )
    assert r.token_type == "bearer"
