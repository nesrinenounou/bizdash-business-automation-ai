from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from . import models, security
from .cache import cache
from .db import Base, SessionLocal, engine
from .routers import auth, catalog, users
from .services import ServiceError


@asynccontextmanager
async def lifespan(_: FastAPI):
    import os
    Base.metadata.create_all(engine)
    email, pw = (os.getenv("ADMIN_EMAIL") or "").strip().lower(), os.getenv("ADMIN_PASSWORD")
    if email and pw:
        with SessionLocal() as db:
            if not db.scalar(select(models.User).where(models.User.email == email)):
                db.add(models.User(email=email, password_hash=security.hash_password(pw), role="admin", full_name="Administrator"))
                db.commit()
    yield


app = FastAPI(
    title="Business Automation & AI Dashboard API",
    description="Customers, orders, role-based access, user management, audit log, AI triage and n8n notifications.",
    lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json",
)


@app.exception_handler(ServiceError)
async def service_error(_: Request, exc: ServiceError):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status)


for r in (auth.router, users.router, users.avatars, catalog.router):
    app.include_router(r)


@app.get("/api/health", tags=["dashboard"])
def health():
    return {"ok": True, "cache": cache.backend}
