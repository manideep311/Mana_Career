from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MIN_PASSWORD_LENGTH = 10
EMAIL_RE: re.Pattern[str] = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_email(v: str) -> str:
    v = v.strip()
    if not EMAIL_RE.match(v):
        raise ValueError("enter a valid email address")
    return v


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("full_name must not be blank")
        return v


class LoginIn(BaseModel):
    email: str
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _clean_email(v)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_admin: bool
    created_at: dt.datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
    user: UserOut


class AccessResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
