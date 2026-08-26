import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


USERNAME_PATTERN = re.compile(r"^[a-z0-9._-]+$")


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["admin", "operator"] = "operator"

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip().lower()
        if not USERNAME_PATTERN.fullmatch(value):
            raise ValueError("Username hanya boleh berisi huruf kecil, angka, titik, _ atau -.")
        return value

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        return " ".join(value.split())


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    role: Literal["admin", "operator"] | None = None
    is_active: bool | None = None


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=200)
