import re
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from .. import models, schemas
from ..config import settings
from ..db import get_db
from ..deps import current_user, require
from ..permissions import Perm
from ..services import UserService

router = APIRouter(prefix="/api/users", tags=["users"])
avatars = APIRouter(prefix="/api/avatars", tags=["users"])
Admin = Depends(require(Perm.USERS_MANAGE))


def read_image(file: UploadFile) -> bytes:
    return file.file.read(settings.max_avatar_bytes + 1)


# ----- my own profile (any role) -----
@router.patch("/me", response_model=schemas.UserOut)
def update_me(body: schemas.ProfileUpdate, user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return UserService(db).update_profile(user, body.model_dump(exclude_unset=True))


@router.post("/me/avatar", response_model=schemas.UserOut)
def set_my_avatar(file: UploadFile = File(...), user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return UserService(db).set_avatar(user, user, read_image(file))


@router.delete("/me/avatar", response_model=schemas.UserOut)
def clear_my_avatar(user: models.User = Depends(current_user), db: Session = Depends(get_db)):
    return UserService(db).clear_avatar(user, user)


# ----- administration -----
@router.get("", response_model=list[schemas.UserOut])
def list_users(q: Optional[str] = Query(None, max_length=100), limit: int = Query(200, ge=1, le=500),
               offset: int = Query(0, ge=0), _: models.User = Admin, db: Session = Depends(get_db)):
    return UserService(db).list(q, limit, offset)


@router.post("", response_model=schemas.UserOut, status_code=201)
def create_user(body: schemas.AdminUserCreate, actor: models.User = Admin, db: Session = Depends(get_db)):
    return UserService(db).create(body.email, body.password, body.role, body.full_name, actor)


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, body: schemas.AdminUserUpdate, actor: models.User = Admin, db: Session = Depends(get_db)):
    svc = UserService(db)
    return svc.admin_update(actor, svc.get(user_id), body.model_dump(exclude_unset=True))


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, actor: models.User = Admin, db: Session = Depends(get_db)):
    svc = UserService(db)
    svc.delete(actor, svc.get(user_id))


@router.post("/{user_id}/avatar", response_model=schemas.UserOut)
def set_user_avatar(user_id: int, file: UploadFile = File(...), actor: models.User = Admin, db: Session = Depends(get_db)):
    svc = UserService(db)
    return svc.set_avatar(actor, svc.get(user_id), read_image(file))


@router.delete("/{user_id}/avatar", response_model=schemas.UserOut)
def clear_user_avatar(user_id: int, actor: models.User = Admin, db: Session = Depends(get_db)):
    svc = UserService(db)
    return svc.clear_avatar(actor, svc.get(user_id))


# ----- public avatar files: random 32-hex names, strict pattern, so no path traversal and no guessing -----
@avatars.get("/{name}")
def avatar_file(name: str):
    if not re.fullmatch(r"[0-9a-f]{32}\.(png|jpg|webp)", name):
        raise HTTPException(404, "Not found")
    path = f"{settings.upload_dir}/{name}"
    try:
        return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})
    except Exception:
        raise HTTPException(404, "Not found")
