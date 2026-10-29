from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from .db import Base, engine
from .routers import (
    account,
    admin,
    auth,
    exercises,
    reports,
    scenes,
    sessions,
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
    if "users" in tables:
        cols = {c["name"] for c in insp.get_columns("users")}
        if "token_version" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 0")
                )


_ensure_schema()

app = FastAPI(title="SpeakPal API", version="0.2.0", docs_url=None, redoc_url=None)

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
