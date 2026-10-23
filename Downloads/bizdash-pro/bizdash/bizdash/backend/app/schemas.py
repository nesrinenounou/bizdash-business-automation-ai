from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

Status = Literal["new", "in_progress", "done", "cancelled"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Credentials(BaseModel):
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)


Role = Literal["admin", "agent"]


class UserOut(ORM):
    id: int
    email: str
    role: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    is_active: bool = True
    created_at: datetime


class MeOut(UserOut):
    permissions: list[str]


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)


class AdminUserUpdate(ProfileUpdate):
    role: Optional[Role] = None
    is_active: Optional[bool] = None


class AdminUserCreate(Credentials):
    role: Role = "agent"
    full_name: Optional[str] = Field(default=None, max_length=120)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AuditOut(ORM):
    id: int
    actor: str
    action: str
    target: str
    detail: str
    created_at: datetime


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: Optional[str] = Field(default=None, max_length=40)


class CustomerOut(ORM, CustomerIn):
    id: int
    created_at: datetime


class OrderIn(BaseModel):
    customer_id: int
    title: str = Field(min_length=1, max_length=200)
    amount: float = Field(ge=0)
    message: Optional[str] = Field(default=None, max_length=5000)


class OrderUpdate(BaseModel):
    title: Optional[str] = None
    amount: Optional[float] = Field(default=None, ge=0)
    status: Optional[Status] = None


class OrderOut(ORM):
    id: int
    customer_id: int
    customer_name: str
    title: str
    amount: float
    status: str
    message: Optional[str]
    summary: Optional[str]
    category: Optional[str]
    priority: Optional[str]
    created_at: datetime


class AnalyzeIn(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
