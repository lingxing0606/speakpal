"""知识检索接口（方案 §3.3）：给 MCP server 与外部客户端用的只读包装。

- `GET /api/knowledge/search`：`rag.search`（语法卡 / 口语卡 / 词库）+ 该用户自己的历史错句。
- `GET /api/knowledge/word`：`tools.call("lookup_word")` 的词库词条。
两个接口都走 `get_current_user`，用户历史按登录身份过滤，不返回别人的数据。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as OrmSession

from ..db import get_db
from ..models import User
from ..security import get_current_user
from ..services import rag, tools

router = APIRouter(prefix="/api", tags=["knowledge"])

MAX_QUERY = 200
MAX_K = 10
MAX_TERM = 64


@router.get("/knowledge/search")
def search_knowledge(
    q: str = Query(default="", max_length=MAX_QUERY),
    k: int = Query(default=4, ge=1, le=MAX_K),
    user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """知识库检索 + 当前用户自己的学习历史（k 只作用于知识库，历史固定 3 条）。"""
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="q 不能为空")
    return {
        "knowledge": rag.search(query, k=k),
        "history": rag.search_user_history(db, user.id, query, k=3),
    }


@router.get("/knowledge/word")
def lookup_word(
    term: str = Query(default="", max_length=MAX_TERM),
    user: User = Depends(get_current_user),
):
    """内置词库词条；查不到时 found=false，不报 404（MCP 工具按同结构回给模型）。"""
    word = (term or "").strip()
    if not word:
        raise HTTPException(status_code=400, detail="term 不能为空")
    hit = tools.call("lookup_word", term=word)
    return {"found": bool(hit), **(hit or {"term": word})}
