from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import User
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut
from ..security import create_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


MAX_NICKNAME = 32


@router.post("/register", response_model=TokenOut)
def register(body: RegisterIn, db: OrmSession = Depends(get_db)):
    # 这里用 400 + 中文提示，而不是让 pydantic 报 422：前端只会显示 detail 数组，用户看不懂
    username = (body.username or "").strip()
    if len(username) < 2:
        raise HTTPException(status_code=400, detail="用户名至少 2 个字符，不能只用空格")
    if len(username) > 32:
        raise HTTPException(status_code=400, detail="用户名最多 32 个字符")
    nickname = (body.nickname or "").strip()
    if len(nickname) > MAX_NICKNAME:
        raise HTTPException(status_code=400, detail=f"昵称最多 {MAX_NICKNAME} 个字")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="账号已存在")
    user = User(
        username=username,
        password_hash=hash_password(body.password),
        nickname=nickname or username,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(token=create_token(user.id, user.token_version), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: OrmSession = Depends(get_db)):
    username = (body.username or "").strip()
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=400, detail="账号或密码错误")
    return TokenOut(token=create_token(user.id, user.token_version), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
