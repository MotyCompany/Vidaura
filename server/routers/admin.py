from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional

from server.database import get_db
from server.models import User, Channel, Video, Comment, Like, Subscription
from server.routers.auth import get_current_user

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_USERNAMES = {"admin"}  # добавь нужных юзеров сюда


def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.username not in ADMIN_USERNAMES:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ── Stats ────────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(require_admin)):
    total_users = db.query(func.count(User.id)).scalar()
    total_videos = db.query(func.count(Video.id)).scalar()
    total_channels = db.query(func.count(Channel.id)).scalar()
    total_comments = db.query(func.count(Comment.id)).scalar()
    total_likes = db.query(func.count(Like.id)).scalar()
    total_subs = db.query(func.count(Subscription.id)).scalar()
    total_views = db.query(func.sum(Video.views)).scalar() or 0

    # New last 7 days
    week_ago = datetime.utcnow() - timedelta(days=7)
    new_users = db.query(func.count(User.id)).filter(User.created_at >= week_ago).scalar()
    new_videos = db.query(func.count(Video.id)).filter(Video.created_at >= week_ago).scalar()

    # Daily registrations last 14 days
    daily = []
    for i in range(13, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = db.query(func.count(User.id)).filter(
            User.created_at >= day_start, User.created_at < day_end
        ).scalar()
        daily.append({"date": day_start.strftime("%d.%m"), "users": count})

    return {
        "total_users": total_users,
        "total_videos": total_videos,
        "total_channels": total_channels,
        "total_comments": total_comments,
        "total_likes": total_likes,
        "total_subscriptions": total_subs,
        "total_views": total_views,
        "new_users_week": new_users,
        "new_videos_week": new_videos,
        "daily_registrations": daily,
    }


# ── Users ────────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(
    skip: int = 0, limit: int = 50, search: str = "",
    db: Session = Depends(get_db), _=Depends(require_admin)
):
    q = db.query(User)
    if search:
        q = q.filter(User.username.ilike(f"%{search}%") | User.email.ilike(f"%{search}%"))
    users = q.order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    total = q.count()

    return {
        "total": total,
        "items": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "created_at": u.created_at.isoformat(),
                "channel_id": u.channel.id if u.channel else None,
                "channel_name": u.channel.name if u.channel else None,
                "videos_count": len(u.channel.videos) if u.channel else 0,
                "comments_count": len(u.comments),
            }
            for u in users
        ]
    }


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"deleted": True}


# ── Videos ───────────────────────────────────────────────────────────────────

@router.get("/videos")
def list_videos(
    skip: int = 0, limit: int = 50, search: str = "",
    db: Session = Depends(get_db), _=Depends(require_admin)
):
    q = db.query(Video)
    if search:
        q = q.filter(Video.title.ilike(f"%{search}%"))
    videos = q.order_by(Video.created_at.desc()).offset(skip).limit(limit).all()
    total = q.count()

    return {
        "total": total,
        "items": [
            {
                "id": v.id,
                "title": v.title,
                "channel_id": v.channel_id,
                "channel_name": v.channel.name,
                "owner_username": v.channel.owner.username,
                "views": v.views,
                "likes_count": len(v.likes),
                "comments_count": len(v.comments),
                "is_public": v.is_public,
                "created_at": v.created_at.isoformat(),
            }
            for v in videos
        ]
    }


@router.patch("/videos/{video_id}/visibility")
def toggle_visibility(video_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    video.is_public = not video.is_public
    db.commit()
    return {"is_public": video.is_public}


@router.delete("/videos/{video_id}")
def admin_delete_video(video_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    import os
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if os.path.exists(video.file_path):
        os.remove(video.file_path)
    db.delete(video)
    db.commit()
    return {"deleted": True}


# ── Comments ─────────────────────────────────────────────────────────────────

@router.get("/comments")
def list_comments(
    skip: int = 0, limit: int = 50,
    db: Session = Depends(get_db), _=Depends(require_admin)
):
    comments = db.query(Comment).order_by(Comment.created_at.desc()).offset(skip).limit(limit).all()
    total = db.query(func.count(Comment.id)).scalar()
    return {
        "total": total,
        "items": [
            {
                "id": c.id,
                "text": c.text,
                "author_username": c.author.username,
                "video_id": c.video_id,
                "video_title": c.video.title,
                "created_at": c.created_at.isoformat(),
            }
            for c in comments
        ]
    }


@router.delete("/comments/{comment_id}")
def admin_delete_comment(comment_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    db.delete(comment)
    db.commit()
    return {"deleted": True}


# ── Channels ──────────────────────────────────────────────────────────────────

@router.get("/channels")
def list_channels(
    skip: int = 0, limit: int = 50, search: str = "",
    db: Session = Depends(get_db), _=Depends(require_admin)
):
    q = db.query(Channel)
    if search:
        q = q.filter(Channel.name.ilike(f"%{search}%"))
    channels = q.order_by(Channel.created_at.desc()).offset(skip).limit(limit).all()
    total = q.count()
    return {
        "total": total,
        "items": [
            {
                "id": ch.id,
                "name": ch.name,
                "owner_username": ch.owner.username,
                "subscribers_count": len(ch.subscribers),
                "videos_count": len(ch.videos),
                "created_at": ch.created_at.isoformat(),
            }
            for ch in channels
        ]
    }
