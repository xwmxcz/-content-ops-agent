"""Public account API shapes; credential rules are owned by passwords.py."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.api.passwords import normalize_username, validate_password


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(max_length=128)
    password: str = Field(max_length=128)

    @field_validator("username")
    @classmethod
    def username_valid(cls, value: str) -> str:
        return normalize_username(value)

    @field_validator("password")
    @classmethod
    def password_valid(cls, value: str) -> str:
        return validate_password(value)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)


class PublicUser(BaseModel):
    id: str
    username: str


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int
    user: PublicUser


class AuthStatusResponse(BaseModel):
    authenticated: bool
    user: PublicUser | None = None
