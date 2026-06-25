from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import os, aiofiles

from server.database import get_db
from server.models import Channel, Subscription, User, Video
from server.routers.auth import get_current_user
from server.routers.videos import video_to_out, VideoOut

router = APIRouter(prefix="/channels", tags=["channels"])

BANNER_DIR = "./uploads/banners"
AVATAR_DIR = "./uploads/avatars"
for d in [BANNER_DIR, AVATAR_DIR]:
    os.makedirs(d, exist_ok=True)


class ChannelOut(BaseModel):
    id: int
    owner_id: int
    owner_username: str
    name: str
    description: Optional[str]
    banner_url: Optional[str]
    subscribers_count: int
    videos_count: int
    total_views: int
    created_at: datetime
    subscribed_by_me: bool = False

    class Config:
        from_attributes = True


def channel_to_out(channel: Channel, current_user: Optional[User] = None) -> ChannelOut:
    subscribed = False
    if current_user:
        subscribed = any(s.subscriber_id == current_user.id for s in channel.subscribers)
    total_views = sum(v.views for v in channel.videos)
    return ChannelOut(
        id=channel.id,
        owner_id=channel.owner_id,
        owner_username=channel.owner.username,
        name=channel.name,
        description=channel.description,
        banner_url=channel.banner_url,
        subscribers_count=len(channel.subscribers),
        videos_count=len(channel.videos),
        total_views=total_views,
        created_at=channel.created_at,
        subscribed_by_me=subscribed,
    )


@router.get("/subscriptions/feed", response_model=list[VideoOut])
def subscriptions_feed(
    skip: int = 0, limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub_ids = [s.channel_id for s in current_user.subscriptions]
    if not sub_ids:
        return []
    videos = (
        db.query(Video)
        .filter(Video.channel_id.in_(sub_ids), Video.is_public == True)
        .order_by(Video.created_at.desc())
        .offset(skip).limit(limit).all()
    )
    return [video_to_out(v, current_user) for v in videos]


@router.get("/my", response_model=ChannelOut)
def my_channel(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.channel:
        raise HTTPException(404, "No channel")
    return channel_to_out(current_user.channel, current_user)


@router.get("/{channel_id}", response_model=ChannelOut)
def get_channel(channel_id: int, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Not found")
    return channel_to_out(ch)


@router.get("/{channel_id}/videos", response_model=list[VideoOut])
def get_channel_videos(channel_id: int, skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Not found")
    videos = (
        db.query(Video)
        .filter(Video.channel_id == channel_id, Video.is_public == True)
        .order_by(Video.created_at.desc()).offset(skip).limit(limit).all()
    )
    return [video_to_out(v) for v in videos]


@router.patch("/{channel_id}", response_model=ChannelOut)
async def update_channel(
    channel_id: int,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    banner: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Not found")
    if ch.owner_id != current_user.id:
        raise HTTPException(403, "Forbidden")
    if name:
        ch.name = name
    if description is not None:
        ch.description = description
    if banner and banner.filename:
        import time
        ext = os.path.splitext(banner.filename)[1] or ".jpg"
        fname = f"{current_user.id}_{int(time.time())}{ext}"
        fpath = os.path.join(BANNER_DIR, fname)
        async with aiofiles.open(fpath, "wb") as f:
            await f.write(await banner.read())
        ch.banner_url = f"/uploads/banners/{fname}"
    db.commit()
    db.refresh(ch)
    return channel_to_out(ch, current_user)


@router.post("/{channel_id}/subscribe")
def toggle_subscribe(
    channel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ch = db.query(Channel).filter(Channel.id == channel_id).first()
    if not ch:
        raise HTTPException(404, "Not found")
    if ch.owner_id == current_user.id:
        raise HTTPException(400, "Cannot subscribe to own channel")
    existing = db.query(Subscription).filter(
        Subscription.subscriber_id == current_user.id,
        Subscription.channel_id == channel_id,
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"subscribed": False}
    db.add(Subscription(subscriber_id=current_user.id, channel_id=channel_id))
    db.commit()
    return {"subscribed": True}
