import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import models, security
from .db import get_db
from .permissions import Perm, perms_for

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> models.User:
    try:
        email = security.decode_token(token)["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    user = db.scalar(select(models.User).where(models.User.email == email))
    if not user or not user.is_active:  # a disabled account loses access immediately, token or not
        raise HTTPException(401, "Unknown or disabled user")
    return user


def require(*needed: Perm):
    def dep(user: models.User = Depends(current_user)) -> models.User:
        if not set(needed) <= perms_for(user.role):
            raise HTTPException(403, "You do not have permission to do this")
        return user
    return dep
