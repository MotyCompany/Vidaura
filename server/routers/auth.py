from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import JWTError, jwt
import bcrypt

from server.database import get_db
from server.models import User, Channel

router = APIRouter(prefix="/auth", tags=["auth"])

SECRET_KEY = "vidaura-secret-key-2026-motyco"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


class UserRegister(BaseModel):
    username: str
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    avatar_url: str | None
    created_at: datetime
    channel_id: int | None = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user


@router.post("/register", response_model=Token)
def register(data: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password)
    )
    db.add(user)
    db.flush()

    channel = Channel(owner_id=user.id, name=f"{data.username}'s Channel")
    db.add(channel)
    db.commit()
    db.refresh(user)
    db.refresh(channel)

    token = create_token({"sub": str(user.id)})
    user_out = UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        channel_id=channel.id
    )
    return Token(access_token=token, token_type="bearer", user=user_out)


@router.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_token({"sub": str(user.id)})
    channel = user.channel
    user_out = UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        channel_id=channel.id if channel else None
    )
    return Token(access_token=token, token_type="bearer", user=user_out)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    channel = current_user.channel
    return UserOut(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        avatar_url=current_user.avatar_url,
        created_at=current_user.created_at,
        channel_id=channel.id if channel else None
    )
