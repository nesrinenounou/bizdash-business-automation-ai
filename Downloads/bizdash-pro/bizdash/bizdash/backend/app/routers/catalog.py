from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy.orm import Session
from .. import ai, models, schemas
from ..db import get_db
from ..deps import require
from ..permissions import Perm
from ..services import (AuditService, CustomerService, OrderService, StatsService, order_out, process_order, to_csv)

router = APIRouter(prefix="/api", tags=["catalog"])
Page = dict(limit=Query(200, ge=1, le=500), offset=Query(0, ge=0))


# ----- customers: agents read/create/edit, only admins delete -----
@router.get("/customers", response_model=list[schemas.CustomerOut])
def list_customers(q: Optional[str] = Query(None, max_length=100), limit: int = Page["limit"], offset: int = Page["offset"],
                   _: models.User = Depends(require(Perm.CUSTOMERS_READ)), db: Session = Depends(get_db)):
    return CustomerService(db).list(q, limit, offset)


@router.post("/customers", response_model=schemas.CustomerOut, status_code=201)
def create_customer(body: schemas.CustomerIn, u: models.User = Depends(require(Perm.CUSTOMERS_WRITE)), db: Session = Depends(get_db)):
    return CustomerService(db).create(u, body)


@router.put("/customers/{cid}", response_model=schemas.CustomerOut)
def update_customer(cid: int, body: schemas.CustomerIn, u: models.User = Depends(require(Perm.CUSTOMERS_WRITE)), db: Session = Depends(get_db)):
    return CustomerService(db).update(u, cid, body)


@router.delete("/customers/{cid}", status_code=204)
def delete_customer(cid: int, u: models.User = Depends(require(Perm.CUSTOMERS_DELETE)), db: Session = Depends(get_db)):
    CustomerService(db).delete(u, cid)


# ----- orders -----
@router.get("/orders", response_model=list[schemas.OrderOut])
def list_orders(status: Optional[schemas.Status] = None, limit: int = Page["limit"], offset: int = Page["offset"],
                _: models.User = Depends(require(Perm.ORDERS_READ)), db: Session = Depends(get_db)):
    return [order_out(o) for o in OrderService(db).list(status, limit, offset)]


@router.post("/orders", response_model=schemas.OrderOut, status_code=201)
def create_order(body: schemas.OrderIn, bg: BackgroundTasks, u: models.User = Depends(require(Perm.ORDERS_WRITE)), db: Session = Depends(get_db)):
    o = OrderService(db).create(u, body)
    bg.add_task(process_order, o.id)
    return order_out(o)


@router.patch("/orders/{oid}", response_model=schemas.OrderOut)
def update_order(oid: int, body: schemas.OrderUpdate, u: models.User = Depends(require(Perm.ORDERS_WRITE)), db: Session = Depends(get_db)):
    return order_out(OrderService(db).update(u, oid, body))


@router.delete("/orders/{oid}", status_code=204)
def delete_order(oid: int, u: models.User = Depends(require(Perm.ORDERS_DELETE)), db: Session = Depends(get_db)):
    OrderService(db).delete(u, oid)


# ----- AI, stats, export, audit -----
@router.post("/ai/analyze", tags=["ai"])
def analyze(body: schemas.AnalyzeIn, _: models.User = Depends(require(Perm.AI_ANALYZE))):
    return ai.analyze(body.message)


@router.get("/stats", tags=["dashboard"])
def stats(_: models.User = Depends(require(Perm.STATS_READ)), db: Session = Depends(get_db)):
    return StatsService(db).get()


def _csv(name: str, content: str) -> Response:
    return Response(content, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/export/orders.csv", tags=["export"])
def export_orders(_: models.User = Depends(require(Perm.EXPORT_CSV)), db: Session = Depends(get_db)):
    rows = [(o.id, o.customer.name, o.title, o.amount, o.status, o.category, o.priority, o.created_at.date())
            for o in OrderService(db).list(None, 5000, 0)]
    return _csv("orders.csv", to_csv(["id", "customer", "title", "amount", "status", "category", "priority", "date"], rows))


@router.get("/export/customers.csv", tags=["export"])
def export_customers(_: models.User = Depends(require(Perm.EXPORT_CSV)), db: Session = Depends(get_db)):
    rows = [(c.id, c.name, c.email, c.phone, c.created_at.date()) for c in CustomerService(db).list(None, 5000, 0)]
    return _csv("customers.csv", to_csv(["id", "name", "email", "phone", "added"], rows))


@router.get("/audit", response_model=list[schemas.AuditOut], tags=["admin"])
def audit(limit: int = Page["limit"], offset: int = Page["offset"],
          _: models.User = Depends(require(Perm.AUDIT_READ)), db: Session = Depends(get_db)):
    return AuditService(db).recent(limit, offset)
