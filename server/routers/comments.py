from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from server.database import get_db
from server.models import Comment, Video, User
from server.routers.auth import get_current_user

router = APIRouter(prefix="/comments", tags=["comments"])


class CommentCreate(BaseModel):
    text: str
    parent_id: Optional[int] = None


class CommentOut(BaseModel):
    id: int
    video_id: int
    author_id: int
    author_username: str
    author_avatar: Optional[str]
    parent_id: Optional[int]
    text: str
    created_at: datetime
    replies: list["CommentOut"] = []

    class Config:
        from_attributes = True


def comment_to_out(c: Comment) -> CommentOut:
    return CommentOut(
        id=c.id,
        video_id=c.video_id,
        author_id=c.author_id,
        author_username=c.author.username,
        author_avatar=c.author.avatar_url,
        parent_id=c.parent_id,
        text=c.text,
        created_at=c.created_at,
        replies=[comment_to_out(r) for r in c.replies],
    )


@router.get("/video/{video_id}", response_model=list[CommentOut])
def get_comments(video_id: int, db: Session = Depends(get_db)):
    if not db.query(Video).filter(Video.id == video_id).first():
        raise HTTPException(404, "Video not found")
    top = (
        db.query(Comment)
        .filter(Comment.video_id == video_id, Comment.parent_id == None)
        .order_by(Comment.created_at.asc())
        .all()
    )
    return [comment_to_out(c) for c in top]


@router.post("/video/{video_id}", response_model=CommentOut)
def add_comment(
    video_id: int,
    data: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not db.query(Video).filter(Video.id == video_id).first():
        raise HTTPException(404, "Video not found")
    if data.parent_id:
        parent = db.query(Comment).filter(Comment.id == data.parent_id).first()
        if not parent or parent.video_id != video_id:
            raise HTTPException(400, "Invalid parent")
    c = Comment(video_id=video_id, author_id=current_user.id, parent_id=data.parent_id, text=data.text)
    db.add(c)
    db.commit()
    db.refresh(c)
    return comment_to_out(c)


@router.delete("/{comment_id}")
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    c = db.query(Comment).filter(Comment.id == comment_id).first()
    if not c:
        raise HTTPException(404, "Not found")
    if c.author_id != current_user.id:
        raise HTTPException(403, "Forbidden")
    db.delete(c)
    db.commit()
    return {"deleted": True}
