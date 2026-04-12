from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class UserProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    display_name: str
    role: str
    department: str
    status: str


class LoginResponse(BaseModel):
    token: str
    user: UserProfileRead


class DemoAccountRead(BaseModel):
    username: str
    display_name: str
    role: str
    department: str
