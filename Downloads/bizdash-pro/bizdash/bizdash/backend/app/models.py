from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="agent")  # admin | agent
    full_name: Mapped[Optional[str]] = mapped_column(String(120), default=None)
    phone: Mapped[Optional[str]] = mapped_column(String(40), default=None)
    avatar: Mapped[Optional[str]] = mapped_column(String(80), default=None)  # random file name, never user input
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(40), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    orders: Mapped[list["Order"]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)  # new|in_progress|done|cancelled
    message: Mapped[Optional[str]] = mapped_column(Text, default=None)  # raw customer message
    summary: Mapped[Optional[str]] = mapped_column(Text, default=None)  # AI
    category: Mapped[Optional[str]] = mapped_column(String(30), default=None)  # AI
    priority: Mapped[Optional[str]] = mapped_column(String(10), default=None)  # AI
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    customer: Mapped[Customer] = relationship(back_populates="orders")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    target: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
