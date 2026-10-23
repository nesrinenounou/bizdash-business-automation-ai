from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session
from .. import models, schemas, security
from ..db import get_db
from ..deps import current_user
from ..permissions import perms_for
from ..services import UserService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=schemas.UserOut, status_code=201)
def register(body: schemas.Credentials, db: Session = Depends(get_db)):
    return UserService(db).create(body.email, body.password)  # open sign-up is always least-privilege


@router.post("/login")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form.username.strip().lower()
    key = f"{request.client.host if request.client else '?'}:{email}"
    if security.throttled(key):
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    user = db.scalar(select(models.User).where(models.User.email == email))
    if not user or not security.verify_password(form.password, user.password_hash):
        security.record_failure(key)
        raise HTTPException(401, "Wrong email or password")
    if not user.is_active:
        raise HTTPException(403, "This account is disabled. Contact an administrator.")
    security.clear_failures(key)
    return {"access_token": security.create_token(user.email, user.role), "token_type": "bearer"}


@router.get("/me", response_model=schemas.MeOut)
def me(user: models.User = Depends(current_user)):
    cols = {c.name: getattr(user, c.name) for c in user.__table__.columns}
    return schemas.MeOut.model_validate({**cols, "permissions": sorted(p.value for p in perms_for(user.role))})


@router.post("/password", status_code=204)
def change_password(body: schemas.PasswordChange, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    UserService(db).change_password(user, body.current_password, body.new_password)
