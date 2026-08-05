from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    # Accepts either email or username in a single field for convenience.
    identifier: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    """The signed-in user's own record — the only shape that includes their email.

    Everything shown to *other* users goes through `schemas.social.PublicUser` instead.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: str
    created_at: datetime
    display_name: str | None = None
    bio: str | None = None
    public_portfolio_id: int | None = None
