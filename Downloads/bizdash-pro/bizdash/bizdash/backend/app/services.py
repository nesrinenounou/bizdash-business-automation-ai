"""Business logic. Routers stay thin; every write goes through a service so audit trail,
validation and cache invalidation are applied the same way everywhere."""
import csv, io, json, logging, os, uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload
from . import ai, models, notify, schemas, security
from .cache import cache
from .config import settings
from .db import SessionLocal

STATS_KEY = "stats:v1"
log = logging.getLogger("services")


class ServiceError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


def like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def log(self, actor: str, action: str, target: str = "", detail: str = "") -> None:
        self.db.add(models.AuditLog(actor=actor, action=action, target=target[:255], detail=detail[:2000]))

    def recent(self, limit: int, offset: int):
        stmt = select(models.AuditLog).order_by(models.AuditLog.id.desc()).limit(limit).offset(offset)
        return self.db.scalars(stmt).all()


def sniff_image(data: bytes) -> Optional[str]:
    """Detect the real image type from magic bytes; the client-declared content type is not trusted."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


class UserService:
    def __init__(self, db: Session):
        self.db, self.audit = db, AuditService(db)

    def get(self, uid: int) -> models.User:
        user = self.db.get(models.User, uid)
        if not user:
            raise ServiceError(404, "User not found")
        return user

    def list(self, q: Optional[str], limit: int, offset: int):
        stmt = select(models.User).order_by(models.User.id).limit(limit).offset(offset)
        if q:
            pat = like(q)
            stmt = stmt.where(models.User.email.ilike(pat, escape="\\") | models.User.full_name.ilike(pat, escape="\\"))
        return self.db.scalars(stmt).all()

    def create(self, email: str, password: str, role: str = "agent", full_name: Optional[str] = None,
               actor: Optional[models.User] = None) -> models.User:
        email = email.strip().lower()
        if self.db.scalar(select(models.User).where(models.User.email == email)):
            raise ServiceError(409, "Email already registered")
        user = models.User(email=email, password_hash=security.hash_password(password), role=role, full_name=full_name)
        self.db.add(user)
        self.audit.log(actor.email if actor else email, "user.create", email, f"role={role}")
        self.db.commit(); self.db.refresh(user)
        return user

    def update_profile(self, user: models.User, data: dict) -> models.User:
        for k, v in data.items():
            setattr(user, k, v)
        self.audit.log(user.email, "profile.update", user.email, json.dumps(data))
        self.db.commit(); self.db.refresh(user)
        return user

    def admin_update(self, actor: models.User, user: models.User, data: dict) -> models.User:
        if user.id == actor.id and (data.get("role", user.role) != user.role or data.get("is_active") is False):
            raise ServiceError(400, "You cannot change your own role or deactivate yourself")
        for k, v in data.items():
            setattr(user, k, v)
        self.audit.log(actor.email, "user.update", user.email, json.dumps(data))
        self.db.commit(); self.db.refresh(user)
        return user

    def change_password(self, user: models.User, current: str, new: str) -> None:
        if not security.verify_password(current, user.password_hash):
            raise ServiceError(400, "Current password is wrong")
        user.password_hash = security.hash_password(new)
        self.audit.log(user.email, "password.change", user.email)
        self.db.commit()

    def delete(self, actor: models.User, user: models.User) -> None:
        if user.id == actor.id:
            raise ServiceError(400, "You cannot delete your own account")
        self._remove_file(user.avatar)
        self.audit.log(actor.email, "user.delete", user.email)
        self.db.delete(user); self.db.commit()

    # ----- avatars -----
    def set_avatar(self, actor: models.User, user: models.User, data: bytes) -> models.User:
        if len(data) > settings.max_avatar_bytes:
            raise ServiceError(413, "Image is larger than 2 MB")
        ext = sniff_image(data)
        if not ext:
            raise ServiceError(415, "Use a PNG, JPEG or WebP image")
        os.makedirs(settings.upload_dir, exist_ok=True)
        name = f"{uuid.uuid4().hex}.{ext}"
        with open(os.path.join(settings.upload_dir, name), "wb") as fh:
            fh.write(data)
        self._remove_file(user.avatar)
        user.avatar = name
        self.audit.log(actor.email, "avatar.set", user.email)
        self.db.commit(); self.db.refresh(user)
        return user

    def clear_avatar(self, actor: models.User, user: models.User) -> models.User:
        self._remove_file(user.avatar)
        user.avatar = None
        self.audit.log(actor.email, "avatar.remove", user.email)
        self.db.commit(); self.db.refresh(user)
        return user

    @staticmethod
    def _remove_file(name: Optional[str]) -> None:
        if name:
            try:
                os.remove(os.path.join(settings.upload_dir, name))
            except OSError:
                pass


class CustomerService:
    def __init__(self, db: Session):
        self.db, self.audit = db, AuditService(db)

    def get(self, cid: int) -> models.Customer:
        c = self.db.get(models.Customer, cid)
        if not c:
            raise ServiceError(404, "Customer not found")
        return c

    def list(self, q: Optional[str], limit: int, offset: int):
        stmt = select(models.Customer).order_by(models.Customer.id.desc()).limit(limit).offset(offset)
        if q:
            pat = like(q)
            stmt = stmt.where(models.Customer.name.ilike(pat, escape="\\") | models.Customer.email.ilike(pat, escape="\\"))
        return self.db.scalars(stmt).all()

    def create(self, actor: models.User, body: schemas.CustomerIn) -> models.Customer:
        c = models.Customer(**body.model_dump())
        self.db.add(c); self.db.flush()
        self.audit.log(actor.email, "customer.create", f"#{c.id} {c.name}")
        return self._commit(c)

    def update(self, actor: models.User, cid: int, body: schemas.CustomerIn) -> models.Customer:
        c = self.get(cid)
        for k, v in body.model_dump().items():
            setattr(c, k, v)
        self.audit.log(actor.email, "customer.update", f"#{c.id} {c.name}")
        return self._commit(c)

    def delete(self, actor: models.User, cid: int) -> None:
        c = self.get(cid)
        self.audit.log(actor.email, "customer.delete", f"#{c.id} {c.name}")
        self.db.delete(c); self.db.commit(); cache.delete(STATS_KEY)

    def _commit(self, c: models.Customer) -> models.Customer:
        self.db.commit(); self.db.refresh(c); cache.delete(STATS_KEY)
        return c


def order_out(o: models.Order) -> schemas.OrderOut:
    return schemas.OrderOut.model_validate({**{c.name: getattr(o, c.name) for c in o.__table__.columns},
                                            "customer_name": o.customer.name})


class OrderService:
    def __init__(self, db: Session):
        self.db, self.audit = db, AuditService(db)

    def get(self, oid: int) -> models.Order:
        o = self.db.get(models.Order, oid)
        if not o:
            raise ServiceError(404, "Order not found")
        return o

    def list(self, status: Optional[str], limit: int, offset: int):
        stmt = (select(models.Order).options(joinedload(models.Order.customer))
                .order_by(models.Order.id.desc()).limit(limit).offset(offset))
        if status:
            stmt = stmt.where(models.Order.status == status)
        return self.db.scalars(stmt).all()

    def create(self, actor: models.User, body: schemas.OrderIn) -> models.Order:
        if not self.db.get(models.Customer, body.customer_id):
            raise ServiceError(404, "Customer not found")
        o = models.Order(**body.model_dump())
        self.db.add(o); self.db.flush()
        self.audit.log(actor.email, "order.create", f"#{o.id} {o.title}", f"amount={o.amount}")
        return self._commit(o)

    def update(self, actor: models.User, oid: int, body: schemas.OrderUpdate) -> models.Order:
        o = self.get(oid)
        data = body.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(o, k, v)
        self.audit.log(actor.email, "order.update", f"#{o.id} {o.title}", json.dumps(data))
        return self._commit(o)

    def delete(self, actor: models.User, oid: int) -> None:
        o = self.get(oid)
        self.audit.log(actor.email, "order.delete", f"#{o.id} {o.title}")
        self.db.delete(o); self.db.commit(); cache.delete(STATS_KEY)

    def _commit(self, o: models.Order) -> models.Order:
        self.db.commit(); self.db.refresh(o); cache.delete(STATS_KEY)
        return o


def process_order(order_id: int) -> None:
    """Background job: AI triage then n8n notification. Failures never block order creation."""
    with SessionLocal() as db:
        o = db.get(models.Order, order_id)
        if not o:
            return
        if o.message:
            r = ai.analyze(o.message)
            o.summary, o.category, o.priority = r["summary"], r["category"], r["priority"]
            db.commit()
        notify.send_new_order({"order_id": o.id, "title": o.title, "amount": o.amount,
                               "customer": o.customer.name, "customer_email": o.customer.email,
                               "category": o.category, "priority": o.priority, "summary": o.summary})


class StatsService:
    def __init__(self, db: Session):
        self.db = db

    def get(self) -> dict:
        cached = cache.get(STATS_KEY)
        if cached:
            return json.loads(cached)
        data = self.compute()
        cache.set(STATS_KEY, json.dumps(data), settings.stats_ttl)
        return data

    def compute(self) -> dict:
        O, db = models.Order, self.db
        by_status = dict(db.execute(select(O.status, func.count()).group_by(O.status)).all())
        by_category = dict(db.execute(select(O.category, func.count()).where(O.category.is_not(None)).group_by(O.category)).all())
        live = db.execute(select(O.created_at, O.amount).where(O.status != "cancelled")).all()
        cust_dates = db.scalars(select(models.Customer.created_at)).all()
        today = datetime.now(timezone.utc)
        cur = (today.year, today.month)
        prev = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        key = lambda d: (d.year, d.month)
        monthly = [0.0] * 12
        for d, amount in live:
            if d.year == today.year:
                monthly[d.month - 1] += amount
        revenue = sum(a for _, a in live)
        return {
            "customers": len(cust_dates), "orders": db.scalar(select(func.count(O.id))),
            "revenue": float(revenue), "avg_order_value": float(revenue / len(live)) if live else 0.0,
            "by_status": by_status, "by_category": by_category, "monthly_revenue": monthly,
            "revenue_this_month": sum(a for d, a in live if key(d) == cur),
            "revenue_last_month": sum(a for d, a in live if key(d) == prev),
            "orders_this_month": sum(1 for d, _ in live if key(d) == cur),
            "orders_last_month": sum(1 for d, _ in live if key(d) == prev),
            "customers_this_month": sum(1 for d in cust_dates if key(d) == cur),
            "customers_last_month": sum(1 for d in cust_dates if key(d) == prev),
        }


def _safe(v) -> str:
    """Neutralise spreadsheet formula injection (=, +, -, @) in exported cells."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def to_csv(header: list[str], rows) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    for r in rows:
        w.writerow([_safe(x) for x in r])
    return buf.getvalue()
