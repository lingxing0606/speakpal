"""SpeakPal MCP server（方案 §3.1–3.2）：把学习数据与知识库发布成标准 MCP server。

stdio（Claude Desktop 等客户端）：
    set SPEAKPAL_TOKEN=<设置页复制的令牌>
    backend\\.venv\\Scripts\\python.exe backend\\mcp_server.py

Streamable HTTP（MCP Inspector 演示）：
    backend\\.venv\\Scripts\\python.exe backend\\mcp_server.py --transport streamable-http --port 8010

只通过 HTTP 调后端 API，不直连数据库：鉴权、用户隔离都复用后端，也不会和后端抢 SQLite 写锁。
环境变量：`SPEAKPAL_API`（默认 http://127.0.0.1:8000）、`SPEAKPAL_TOKEN`（登录 JWT，必填）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

API_BASE = os.environ.get("SPEAKPAL_API", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("SPEAKPAL_TOKEN", "").strip()
TIMEOUT = 15.0
TOKEN_EXPIRED = "令牌失效，请在 SpeakPal 设置页重新复制"
TOKEN_MISSING = "未配置 SPEAKPAL_TOKEN：请先在 SpeakPal 设置页复制令牌"

READ_ONLY = ToolAnnotations(read_only_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False)

mcp = MCPServer(
    "SpeakPal",
    instructions=(
        "SpeakPal 英语学习数据：今天该复习什么、最近报告错在哪、查语法卡/词条、"
        "加入生词本、记笔记。会修改用户数据的工具，调用前先向用户确认。"
    ),
)


def _json(data) -> str:
    return json.dumps(data, ensure_ascii=False)


def _api(method: str, path: str, **kwargs):
    """调后端 API；网络/HTTP 错误统一转成 {"error": ...}，不把堆栈抛给模型。"""
    if not TOKEN:
        return {"error": TOKEN_MISSING}
    try:
        with httpx.Client(
            base_url=API_BASE,
            headers={"Authorization": f"Bearer {TOKEN}"},
            timeout=TIMEOUT,
        ) as client:
            resp = client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        return {"error": f"连不上 SpeakPal 后端 {API_BASE}（{type(exc).__name__}）"}
    if resp.status_code == 401:
        return {"error": TOKEN_EXPIRED}
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = None
        return {"error": str(detail or f"后端返回 HTTP {resp.status_code}")}
    try:
        return resp.json()
    except ValueError:
        return {"error": "后端返回了无法解析的数据"}


def _failed(data) -> bool:
    return isinstance(data, dict) and "error" in data


def _bounded(value, default: int, low: int, high: int) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(size, high))


@mcp.tool(annotations=READ_ONLY)
def get_today_plan() -> str:
    """今天的复习队列：按单词/拼写/语法/口语/句型分组的到期卡与数量。

    只读，不修改数据。用户问「我今天该复习什么」「今天练什么」时调用。
    """
    return _json(_api("GET", "/api/study/today"))


@mcp.tool(annotations=READ_ONLY)
def get_due_reviews(limit: int = 10) -> str:
    """今天到期、等着复习的学习卡（按到期时间升序，最多 limit 张，默认 10）。只读。"""
    size = _bounded(limit, 10, 1, 50)
    return _json(_api("GET", "/api/study/due", params={"limit": size}))


@mcp.tool(annotations=READ_ONLY)
def get_recent_reports(limit: int = 3) -> str:
    """最近几次练习的报告摘要：场景、总分、档位，以及最多 5 条纠错。

    只读。用户问「我最近练得怎么样」「上次错在哪」时调用。
    """
    size = _bounded(limit, 3, 1, 10)
    rows = _api("GET", "/api/sessions", params={"limit": size})
    if _failed(rows) or not isinstance(rows, list):
        return _json(rows if _failed(rows) else {"error": "没有取到练习记录"})
    out = []
    for row in rows[:size]:
        item = {
            "session_id": row.get("id"),
            "scene": row.get("scene_name"),
            "status": row.get("status"),
            "created_at": row.get("created_at"),
        }
        if not row.get("report_id"):
            out.append(item)
            continue
        report = _api("GET", f"/api/sessions/{row.get('id')}/report")
        if _failed(report):
            out.append(item)
            continue
        fixes = report.get("sentence_fixes") or []
        item.update(
            {
                "total_score": report.get("total_score"),
                "band": report.get("band"),
                "cefr": report.get("cefr"),
                "comment": report.get("comment"),
                "fixes": [
                    {
                        "original": fix.get("original"),
                        "better": fix.get("better"),
                        "reason": fix.get("reason"),
                        "error_type": fix.get("error_type"),
                    }
                    for fix in fixes[:5]
                    if isinstance(fix, dict)
                ],
            }
        )
        out.append(item)
    return _json(out)


@mcp.tool(annotations=READ_ONLY)
def get_weak_points() -> str:
    """学习面板里的薄弱点：连续打卡、各维度均分、近 7 天 band 变化。

    只读。热力图不返回（96 天的逐日数据对回答没必要）。
    """
    data = _api("GET", "/api/me/dashboard")
    if _failed(data):
        return _json(data)
    return _json(
        {
            "today": data.get("today"),
            "current_streak": data.get("current_streak"),
            "longest_streak": data.get("longest_streak"),
            "practiced_today": data.get("practiced_today"),
            "scored_reports": data.get("scored_reports"),
            "dimensions": data.get("dimensions"),
            "week": data.get("week"),
        }
    )


@mcp.tool(annotations=READ_ONLY)
def search_knowledge(query: str, k: int = 4) -> str:
    """检索语法卡、口语卡、词库，以及该用户自己的历史错句。只读。

    k 是知识库条数（1–10，默认 4）；历史错句固定最多 3 条，按登录身份过滤。
    """
    size = _bounded(k, 4, 1, 10)
    return _json(_api("GET", "/api/knowledge/search", params={"q": query, "k": size}))


@mcp.tool(annotations=READ_ONLY)
def lookup_word(term: str) -> str:
    """查内置词库的一个英文词：音标、词性、中文释义、例句、同反义词。只读。"""
    return _json(_api("GET", "/api/knowledge/word", params={"term": term}))


@mcp.tool(annotations=WRITE)
def add_word_to_review(term: str) -> str:
    """把单词加入生词本并安排复习。会修改用户数据，调用前先向用户确认。"""
    return _json(
        _api(
            "POST",
            "/api/study/words/learn",
            json={"term": term, "recognized": True, "spelled": True, "used": True},
        )
    )


@mcp.tool(annotations=WRITE)
def add_note(title: str = "", body: str = "") -> str:
    """新建一条学习笔记（标题可留空，正文首行会当标题）。会修改用户数据，调用前先向用户确认。"""
    return _json(_api("POST", "/api/notes", json={"title": title or None, "body": body}))


@mcp.resource("speakpal://grammar/{card_id}")
def grammar_card(card_id: str) -> str:
    """语法卡原文（card_id 形如 tenses-01）。只读。"""
    data = _api("GET", "/api/study/grammar")
    if _failed(data):
        return _json(data)
    for group in data.get("groups") or []:
        for card in group.get("items") or []:
            if str(card.get("id")) == card_id:
                return _json(card)
    return _json({"error": f"没有语法卡 {card_id}"})


@mcp.resource("speakpal://spoken/{item_id}")
def spoken_card(item_id: str) -> str:
    """口语卡原文（item_id 形如 spoken-01）。只读。"""
    data = _api("GET", "/api/study/spoken")
    if _failed(data):
        return _json(data)
    for card in data.get("items") or []:
        if str(card.get("id")) == item_id:
            return _json(card)
    return _json({"error": f"没有口语卡 {item_id}"})


def main() -> None:
    parser = argparse.ArgumentParser(description="SpeakPal MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="stdio 供 Claude Desktop；streamable-http 供 MCP Inspector 演示",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    if not TOKEN:
        print(f"缺少 SPEAKPAL_TOKEN。{TOKEN_MISSING}", file=sys.stderr)
        raise SystemExit(1)
    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
