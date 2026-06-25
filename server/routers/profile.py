from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import os, aiofiles, time

from server.database import get_db
from server.models import User
from server.routers.auth import get_current_user, hash_password, verify_password

router = APIRouter(prefix="/profile", tags=["profile"])

AVATAR_DIR = "./uploads/avatars"
os.makedirs(AVATAR_DIR, exist_ok=True)


class ProfileOut(BaseModel):
    id: int
    username: str
    email: str
    bio: Optional[str]
    avatar_url: Optional[str]
    channel_id: Optional[int]
    class Config:
        from_attributes = True


@router.get("/user/{username}", response_model=ProfileOut)
def get_profile(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(404, "User not found")
    return ProfileOut(
        id=user.id, username=user.username, email=user.email,
        bio=user.bio, avatar_url=user.avatar_url,
        channel_id=user.channel.id if user.channel else None,
    )


@router.patch("/me", response_model=ProfileOut)
async def update_profile(
    bio: Optional[str] = Form(None),
    avatar: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if bio is not None:
        current_user.bio = bio
    if avatar and avatar.filename:
        ext = os.path.splitext(avatar.filename)[1] or ".jpg"
        fname = f"{current_user.id}_{int(time.time())}{ext}"
        fpath = os.path.join(AVATAR_DIR, fname)
        async with aiofiles.open(fpath, "wb") as f:
            await f.write(await avatar.read())
        current_user.avatar_url = f"/uploads/avatars/{fname}"
    db.commit()
    db.refresh(current_user)
    return ProfileOut(
        id=current_user.id, username=current_user.username, email=current_user.email,
        bio=current_user.bio, avatar_url=current_user.avatar_url,
        channel_id=current_user.channel.id if current_user.channel else None,
    )


@router.post("/me/change-password")
def change_password(
    old_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(old_password, current_user.hashed_password):
        raise HTTPException(400, "Wrong current password")
    if len(new_password) < 6:
        raise HTTPException(400, "Password too short (min 6)")
    current_user.hashed_password = hash_password(new_password)
    db.commit()
    return {"ok": True}
