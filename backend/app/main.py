from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from .config import settings
from .db import Base, engine
from .routers import (
    account,
    admin,
    auth,
    exercises,
    reports,
    scenes,
    sessions,
    study,
    system,
    tts,
)

Base.metadata.create_all(bind=engine)


def _ensure_schema():
    """给旧库补列（SQLite 不支持 ADD COLUMN IF NOT EXISTS，只能先查）。

    只加列、不改不删，旧数据保持可读；band 为空的旧报告前端按“无档位”处理。
    """
    insp = inspect(engine)
    tables = insp.get_table_names()
    report_cols = {
        "features_json": "TEXT DEFAULT '{}'",
        "bands_json": "TEXT DEFAULT '{}'",
        "band": "REAL",
        "cefr": "VARCHAR(8)",
        "source": "VARCHAR(16) DEFAULT 'llm'",
        "mock_reason": "VARCHAR(24)",
        "answer_mode": "VARCHAR(8)",
        "comparable_band": "REAL",
        "scoring_json": "TEXT DEFAULT '{}'",
        "plan_json": "TEXT DEFAULT '{}'",
    }
    if "reports" in tables:
        cols = {c["name"] for c in insp.get_columns("reports")}
        for name, ddl in report_cols.items():
            if name not in cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE reports ADD COLUMN {name} {ddl}"))
    if "turns" in tables:
        cols = {c["name"] for c in insp.get_columns("turns")}
        turn_cols = {
            "audio_json": "TEXT DEFAULT '{}'",
            # 旧对话默认按录音算（当时只有录音入口）
            "input_mode": "VARCHAR(8) DEFAULT 'voice'",
        }
        for name, ddl in turn_cols.items():
            if name not in cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE turns ADD COLUMN {name} {ddl}"))
    if "sessions" in tables:
        cols = {c["name"] for c in insp.get_columns("sessions")}
        if "plan_json" not in cols:
            # 旧会话没有 Agent 计划：按空 plan 处理，结束时机仍走原来的 4 轮口径
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE sessions ADD COLUMN plan_json TEXT DEFAULT '{}'"))
    if "users" in tables:
        cols = {c["name"] for c in insp.get_columns("users")}
        if "token_version" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0")
                )
        # 设置页偏好（难度 / 新词范围），旧库补列
        user_prefs = {
            "practice_difficulty": "VARCHAR(16) DEFAULT 'medium'",
            "word_scope": "VARCHAR(16) DEFAULT 'cet4'",
            # 报告默认量表：旧库补列后按默认值读，不需要回填
            "report_scale": "VARCHAR(8) DEFAULT 'ielts'",
        }
        for name, ddl in user_prefs.items():
            if name not in cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))
    if "notes" in tables:
        cols = {c["name"] for c in insp.get_columns("notes")}
        # 早期版本的笔记表用 content 存正文，现在的模型叫 body，查列表会直接 500（用户截图报过）
        if "body" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE notes ADD COLUMN body TEXT DEFAULT ''"))
                if "content" in cols:
                    conn.execute(text("UPDATE notes SET body = COALESCE(content, '')"))
        if "updated_at" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE notes ADD COLUMN updated_at DATETIME"))
                conn.execute(text("UPDATE notes SET updated_at = created_at WHERE updated_at IS NULL"))
        # 迁完之后旧列 content / learning_item_id 仍留在表里：同一个正文两个列并存，
        # 还挂着一个已删表（learning_items）的外键，翻库说不清哪个是真身。
        # 数据为空或有值都能重建，正文取 body（没有就退回 content）。
        if "content" in cols or "learning_item_id" in cols:
            body_expr = (
                "COALESCE(body, content, '')"
                if {"body", "content"} <= cols
                else ("COALESCE(body, '')" if "body" in cols else "COALESCE(content, '')")
            )
            with engine.begin() as conn:
                conn.execute(text("PRAGMA foreign_keys=OFF"))
                conn.execute(
                    text(
                        "CREATE TABLE notes_clean ("
                        "id INTEGER NOT NULL PRIMARY KEY, "
                        "user_id INTEGER NOT NULL, "
                        "title VARCHAR(128), "
                        "body TEXT, "
                        "session_id INTEGER, "
                        "created_at DATETIME, "
                        "updated_at DATETIME, "
                        "FOREIGN KEY(user_id) REFERENCES users (id), "
                        "FOREIGN KEY(session_id) REFERENCES sessions (id))"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO notes_clean (id, user_id, title, body, session_id, created_at, updated_at) "
                        f"SELECT id, user_id, title, {body_expr}, session_id, created_at, "
                        "COALESCE(updated_at, created_at) FROM notes"
                    )
                )
                conn.execute(text("DROP TABLE notes"))
                conn.execute(text("ALTER TABLE notes_clean RENAME TO notes"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notes_user_id ON notes (user_id)"))
                conn.execute(text("PRAGMA foreign_keys=ON"))
    if "study_items" in tables:
        cols = {c["name"] for c in insp.get_columns("study_items")}
        if "related_json" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE study_items ADD COLUMN related_json TEXT DEFAULT '{}'"))
        if "source" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE study_items ADD COLUMN source VARCHAR(16) DEFAULT ''"))


_ensure_schema()

app = FastAPI(title="SpeakPal API", version="0.2.0", docs_url=None, redoc_url=None)

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

app.add_middleware(
    CORSMiddleware,
    # 白名单见 CORS_ORIGINS；认证走 Authorization 头，不需要 Cookie 凭证
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    # 401 的原因码放在响应头，跨域部署时前端要能读到它
    expose_headers=["X-Auth-Reason"],
)

app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(scenes.router)
app.include_router(sessions.router)
app.include_router(reports.router)
app.include_router(account.router)
app.include_router(system.router)
app.include_router(exercises.router)
app.include_router(tts.router)
app.include_router(study.router)


_ADMIN_HTML = _STATIC_DIR / "admin.html"


def _admin_page() -> HTMLResponse:
    return HTMLResponse(_ADMIN_HTML.read_text(encoding="utf-8"))


@app.get("/docs", include_in_schema=False)
def custom_docs():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " · API 文档",
        swagger_js_url="/static/swagger/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger/swagger-ui.css",
        swagger_favicon_url="/static/swagger/favicon-32x32.png",
    )


@app.get("/", response_class=HTMLResponse)
def root():
    return _admin_page()


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return _admin_page()


@app.get("/api/health")
def health():
    return {"status": "ok"}
