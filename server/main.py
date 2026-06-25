import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.database import engine
from server import models
from server.routers import auth, videos, channels, comments, admin, profile

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Vidaura API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

for d in ["./uploads/videos","./uploads/thumbnails","./uploads/subtitles",
          "./uploads/banners","./uploads/avatars"]:
    os.makedirs(d, exist_ok=True)

app.mount("/uploads", StaticFiles(directory="./uploads"), name="uploads")

app.include_router(auth.router)
app.include_router(videos.router)
app.include_router(channels.router)
app.include_router(comments.router)
app.include_router(admin.router)
app.include_router(profile.router)

@app.get("/")
def root():
    return {"service": "Vidaura API", "version": "2.0.0", "company": "MotyCo"}
