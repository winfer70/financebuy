from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr

from ..db import get_db
from ..models import User
from ..auth import hash_password, verify_password, create_access_token

router = APIRouter()


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    first_name: str = ""
    last_name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    first_name: str
    last_name: str


@router.post("/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db)):
    async with db.begin():
        existing = await db.execute(select(User).where(User.email == payload.email))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already registered")
        user = User(
            email=payload.email,
            password_hash=hash_password(payload.password),
            first_name=payload.first_name,
            last_name=payload.last_name,
        )
        db.add(user)
    await db.refresh(user)
    token = create_access_token(str(user.user_id))
    return AuthOut(access_token=token, user_id=str(user.user_id),
                   email=user.email, first_name=user.first_name or "",
                   last_name=user.last_name or "")


@router.post("/login", response_model=AuthOut)
async def login(payload: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(str(user.user_id))
    return AuthOut(access_token=token, user_id=str(user.user_id),
                   email=user.email, first_name=user.first_name or "",
                   last_name=user.last_name or "")
