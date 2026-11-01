import base64
import hashlib
import hmac
import os
import time

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as OrmSession

from .config import settings
from .db import get_db
from .models import User

bearer = HTTPBearer(auto_error=False)

PASSWORD_MIN, PASSWORD_MAX = 6, 64


def check_password_rule(password: str) -> None:
    """新密码统一规则（注册 / 改密 / 管理员重置）。旧的短密码照常能登录。"""
    if len(password) < PASSWORD_MIN or len(password) > PASSWORD_MAX:
        raise HTTPException(status_code=400, detail=f"密码要 {PASSWORD_MIN}–{PASSWORD_MAX} 位")


class LoginLimiter:
    """进程内的登录失败计数：同一 IP+账号 在窗口内失败太多次就暂时拒绝。

    单进程演示够用；多进程部署要换成 Redis 之类的共享存储。
    """

    def __init__(self, max_fails: int = 5, window_sec: int = 300):
        self.max_fails = max_fails
        self.window_sec = window_sec
        self._fails: dict[str, list[float]] = {}

    def _recent(self, key: str, now: float) -> list[float]:
        hits = [t for t in self._fails.get(key, []) if now - t < self.window_sec]
        if hits:
            self._fails[key] = hits
        else:
            self._fails.pop(key, None)
        return hits

    def retry_after(self, key: str) -> int:
        """还要等几秒；0 表示可以尝试。"""
        now = time.time()
        hits = self._recent(key, now)
        if len(hits) < self.max_fails:
            return 0
        return max(1, int(self.window_sec - (now - hits[0])))

    def fail(self, key: str) -> None:
        now = time.time()
        self._recent(key, now)
        self._fails.setdefault(key, []).append(now)

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)


login_limiter = LoginLimiter()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, dk_b64 = stored.split("$", 1)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def create_token(user_id: int, token_version: int = 0) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "tv": int(token_version or 0),
        "iat": now,
        "exp": now + settings.jwt_expire_minutes * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _unauthorized(reason: str, message: str) -> HTTPException:
    """401 统一带原因码，前端据此决定提示文案（改密 vs 过期 vs 注销）。

    放响应头而不是 body：body 的 detail 保持字符串，现有调用方不用改；
    前端读 error.response.headers['x-auth-reason'] 即可。
    """
    return HTTPException(
        status_code=401,
        detail=message,
        headers={"X-Auth-Reason": reason},
    )


def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(bearer),
    db: OrmSession = Depends(get_db),
) -> User:
    if cred is None:
        raise _unauthorized("unauthenticated", "未登录")
    try:
        payload = jwt.decode(
            cred.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = int(payload.get("sub"))
        token_version = int(payload.get("tv", 0))
    except Exception:
        raise _unauthorized("token_invalid", "登录已失效，请重新登录")
    user = db.get(User, user_id)
    if not user:
        raise _unauthorized("user_gone", "账号已注销，请重新注册")
    # 改过密码后 token_version 会 +1，旧设备上的 token 全部作废
    if token_version != int(user.token_version or 0):
        raise _unauthorized("password_changed", "密码已修改，请重新登录")
    return user
