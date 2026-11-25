from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserRegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Full name of the passenger")
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(..., min_length=8, max_length=128, description="Password (at least 8 characters)")


class UserLoginRequest(BaseModel):
    email: EmailStr = Field(..., description="Registered email address")
    password: str = Field(..., description="Account password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    role: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(..., description="Registered account email")


class ForgotPasswordResponse(BaseModel):
    message: str
    dev_reset_token: Optional[str] = Field(
        default=None,
        description="Development-only token simulation. Not returned in production environments."
    )


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, description="Password reset token received")
    new_password: str = Field(..., min_length=8, max_length=128, description="New password")


class MessageResponse(BaseModel):
    message: str
