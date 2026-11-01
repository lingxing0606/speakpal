from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import User
from ..schemas import LoginIn, RegisterIn, TokenOut, UserOut
from ..security import (
    check_password_rule,
    create_token,
    get_current_user,
    hash_password,
    login_limiter,
    verify_password,
)

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
    check_password_rule(body.password or "")
    # 唯一性按小写归一：walkB 和 WalkB 视为同一个账号，避免近似名和「输错大小写登不进去」
    if db.query(User).filter(func.lower(User.username) == username.lower()).first():
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
def login(body: LoginIn, request: Request, db: OrmSession = Depends(get_db)):
    username = (body.username or "").strip()
    client_ip = request.client.host if request.client else "?"
    limit_key = f"{client_ip}|{username.lower()}"
    wait = login_limiter.retry_after(limit_key)
    if wait:
        # 429 而不是 401：前端拦截器把 401 当登录失效
        raise HTTPException(
            status_code=429,
            detail=f"密码错误次数太多，请 {wait} 秒后再试",
            headers={"Retry-After": str(wait)},
        )
    # 登录也不区分大小写（注册时已按小写归一保证唯一）
    user = db.query(User).filter(func.lower(User.username) == username.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        login_limiter.fail(limit_key)
        raise HTTPException(status_code=400, detail="账号或密码错误")
    login_limiter.reset(limit_key)
    return TokenOut(token=create_token(user.id, user.token_version), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
