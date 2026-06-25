import os
import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from server.database import get_db
from server.models import Video, Channel, Like, User
from server.routers.auth import get_current_user

router = APIRouter(prefix="/videos", tags=["videos"])

UPLOAD_DIR = "./uploads/videos"
THUMB_DIR  = "./uploads/thumbnails"
SUBS_DIR   = "./uploads/subtitles"
for d in [UPLOAD_DIR, THUMB_DIR, SUBS_DIR]:
    os.makedirs(d, exist_ok=True)

ALLOWED_VIDEO  = {"video/mp4","video/webm","video/avi","video/x-matroska","video/quicktime","video/x-msvideo"}
ALLOWED_IMAGE  = {"image/jpeg","image/png","image/webp","image/gif"}


class VideoOut(BaseModel):
    id: int
    channel_id: int
    channel_name: str
    owner_username: str
    title: str
    description: Optional[str]
    thumbnail_url: Optional[str]
    subtitle_url: Optional[str]
    duration: Optional[int]
    views: int
    likes_count: int
    comments_count: int
    is_public: bool
    created_at: datetime
    liked_by_me: bool = False

    class Config:
        from_attributes = True


def video_to_out(video: Video, current_user: Optional[User] = None) -> VideoOut:
    liked_by_me = False
    if current_user:
        liked_by_me = any(l.user_id == current_user.id for l in video.likes)
    return VideoOut(
        id=video.id,
        channel_id=video.channel_id,
        channel_name=video.channel.name,
        owner_username=video.channel.owner.username,
        title=video.title,
        description=video.description,
        thumbnail_url=video.thumbnail_url,
        subtitle_url=video.subtitle_url,
        duration=video.duration,
        views=video.views,
        likes_count=len(video.likes),
        comments_count=len(video.comments),
        is_public=video.is_public,
        created_at=video.created_at,
        liked_by_me=liked_by_me,
    )


def _save_path(directory: str, user_id: int, ext: str) -> tuple[str, str]:
    import time
    fname = f"{user_id}_{int(time.time())}{ext}"
    return os.path.join(directory, fname), f"/{directory.lstrip('./')}/{fname}"


@router.post("/upload", response_model=VideoOut)
async def upload_video(
    title: str = Form(...),
    description: str = Form(""),
    is_public: bool = Form(True),
    file: UploadFile = File(...),
    thumbnail: Optional[UploadFile] = File(None),
    subtitles: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    channel = current_user.channel
    if not channel:
        raise HTTPException(400, "No channel")

    ext = os.path.splitext(file.filename or "")[1] or ".mp4"
    fpath, _ = _save_path(UPLOAD_DIR, current_user.id, ext)
    async with aiofiles.open(fpath, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            await f.write(chunk)

    thumb_url = None
    if thumbnail and thumbnail.filename:
        te = os.path.splitext(thumbnail.filename)[1] or ".jpg"
        tp, thumb_url = _save_path(THUMB_DIR, current_user.id, te)
        async with aiofiles.open(tp, "wb") as f:
            await f.write(await thumbnail.read())

    sub_url = None
    if subtitles and subtitles.filename:
        sp, sub_url = _save_path(SUBS_DIR, current_user.id, ".srt")
        async with aiofiles.open(sp, "wb") as f:
            await f.write(await subtitles.read())

    video = Video(
        channel_id=channel.id,
        title=title,
        description=description,
        file_path=fpath,
        thumbnail_url=thumb_url,
        subtitle_url=sub_url,
        is_public=is_public,
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    return video_to_out(video, current_user)


@router.patch("/{video_id}", response_model=VideoOut)
async def update_video(
    video_id: int,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    is_public: Optional[bool] = Form(None),
    thumbnail: Optional[UploadFile] = File(None),
    subtitles: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "Not found")
    if video.channel.owner_id != current_user.id:
        raise HTTPException(403, "Forbidden")

    if title is not None:
        video.title = title
    if description is not None:
        video.description = description
    if is_public is not None:
        video.is_public = is_public

    if thumbnail and thumbnail.filename:
        te = os.path.splitext(thumbnail.filename)[1] or ".jpg"
        tp, thumb_url = _save_path(THUMB_DIR, current_user.id, te)
        async with aiofiles.open(tp, "wb") as f:
            await f.write(await thumbnail.read())
        video.thumbnail_url = thumb_url

    if subtitles and subtitles.filename:
        sp, sub_url = _save_path(SUBS_DIR, current_user.id, ".srt")
        async with aiofiles.open(sp, "wb") as f:
            await f.write(await subtitles.read())
        video.subtitle_url = sub_url

    db.commit()
    db.refresh(video)
    return video_to_out(video, current_user)


@router.get("/stream/{video_id}")
async def stream_video(video_id: int, request: Request, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video or not os.path.exists(video.file_path):
        raise HTTPException(404, "Video not found")

    video.views += 1
    db.commit()

    file_size = os.path.getsize(video.file_path)
    range_header = request.headers.get("range")

    # Determine content type
    ext = os.path.splitext(video.file_path)[1].lower()
    ct_map = {".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska",
              ".avi": "video/x-msvideo", ".mov": "video/quicktime"}
    content_type = ct_map.get(ext, "video/mp4")

    if range_header:
        try:
            start_str, end_str = range_header.replace("bytes=", "").split("-")
            start = int(start_str)
            end = int(end_str) if end_str else min(start + 1024 * 1024, file_size - 1)
        except Exception:
            start, end = 0, file_size - 1
        chunk_size = end - start + 1

        async def stream_range():
            async with aiofiles.open(video.file_path, "rb") as f:
                await f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = await f.read(min(65536, remaining))
                    if not data:
                        break
                    yield data
                    remaining -= len(data)

        return StreamingResponse(
            stream_range(), status_code=206, media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
            },
        )

    async def stream_full():
        async with aiofiles.open(video.file_path, "rb") as f:
            while chunk := await f.read(65536):
                yield chunk

    return StreamingResponse(
        stream_full(), media_type=content_type,
        headers={"Content-Length": str(file_size), "Accept-Ranges": "bytes"},
    )


@router.get("/feed", response_model=list[VideoOut])
def get_feed(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    videos = (
        db.query(Video).filter(Video.is_public == True)
        .order_by(Video.created_at.desc()).offset(skip).limit(limit).all()
    )
    return [video_to_out(v) for v in videos]


@router.get("/search", response_model=list[VideoOut])
def search_videos(q: str, skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    videos = (
        db.query(Video)
        .filter(Video.is_public == True, Video.title.ilike(f"%{q}%"))
        .order_by(Video.created_at.desc()).offset(skip).limit(limit).all()
    )
    return [video_to_out(v) for v in videos]


@router.get("/my", response_model=list[VideoOut])
def my_videos(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.channel:
        return []
    videos = (
        db.query(Video).filter(Video.channel_id == current_user.channel.id)
        .order_by(Video.created_at.desc()).all()
    )
    return [video_to_out(v, current_user) for v in videos]


@router.get("/{video_id}", response_model=VideoOut)
def get_video(video_id: int, db: Session = Depends(get_db)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "Not found")
    return video_to_out(video)


@router.post("/{video_id}/like")
def toggle_like(video_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "Not found")
    existing = db.query(Like).filter(Like.video_id == video_id, Like.user_id == current_user.id).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"liked": False}
    db.add(Like(video_id=video_id, user_id=current_user.id))
    db.commit()
    return {"liked": True}


@router.delete("/{video_id}")
def delete_video(video_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(404, "Not found")
    if video.channel.owner_id != current_user.id:
        raise HTTPException(403, "Forbidden")
    if os.path.exists(video.file_path):
        os.remove(video.file_path)
    db.delete(video)
    db.commit()
    return {"deleted": True}
