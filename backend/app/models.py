from typing import List, Optional
from pydantic import BaseModel, Field


# Auth models
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)
    new_username: Optional[str] = Field(default=None, min_length=3, max_length=64)


class UserOut(BaseModel):
    id: str
    username: str
    role: str = "user"
    must_change_password: bool = False


class AdminUserOut(BaseModel):
    id: str
    username: str
    role: str
    must_change_password: bool
    created_at: str


class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(default=None, min_length=3, max_length=64)
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    role: Optional[str] = Field(default=None, pattern="^(admin|user)$")


class SystemSettings(BaseModel):
    allow_registration: bool = True


class MessageResponse(BaseModel):
    message: str


# Account models
class AccountCreate(BaseModel):
    email: str = Field(min_length=1, max_length=256)
    password: str = Field(default="", max_length=256)
    refresh_token: str = Field(min_length=1)
    client_id: str = Field(min_length=1, max_length=128)
    group_id: Optional[str] = None
    remark: Optional[str] = Field(default=None, max_length=256)


class AccountUpdate(BaseModel):
    email: Optional[str] = Field(default=None, max_length=256)
    password: Optional[str] = Field(default=None, max_length=256)
    refresh_token: Optional[str] = None
    client_id: Optional[str] = Field(default=None, max_length=128)
    group_id: Optional[str] = None
    remark: Optional[str] = Field(default=None, max_length=256)


class AccountOut(BaseModel):
    id: str
    email: str
    client_id: str
    group_id: Optional[str] = None
    remark: Optional[str] = None
    status: str = "unknown"
    last_verified: Optional[str] = None
    created_at: str


class BatchImportRequest(BaseModel):
    data: str = Field(min_length=1, description="Multi-line account data")
    group_id: Optional[str] = None


class BatchDeleteRequest(BaseModel):
    ids: List[str] = Field(min_items=1)


class BatchGroupRequest(BaseModel):
    ids: List[str] = Field(min_items=1)
    group_id: Optional[str] = None  # None means remove from group


# Group models
class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class GroupOut(BaseModel):
    id: str
    name: str


# Mail models
class MailMessage(BaseModel):
    id: str
    subject: Optional[str] = None
    from_address: Optional[str] = None
    from_name: Optional[str] = None
    received_at: Optional[str] = None
    is_read: bool = False
    body_preview: Optional[str] = None


class MailDetail(BaseModel):
    id: str
    subject: Optional[str] = None
    from_address: Optional[str] = None
    from_name: Optional[str] = None
    to: List[str] = []
    cc: List[str] = []
    received_at: Optional[str] = None
    is_read: bool = False
    body_content: Optional[str] = None
    body_type: str = "text"


class MailFolder(BaseModel):
    id: str
    name: str
    unread_count: int = 0
    total_count: int = 0


class VerifyResult(BaseModel):
    account_id: str
    email: str
    valid: bool
    error: Optional[str] = None
