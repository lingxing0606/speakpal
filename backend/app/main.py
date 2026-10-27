from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy import inspect, text

from .db import Base, engine
from .routers import auth, reports, scenes, sessions

Base.metadata.create_all(bind=engine)


def _ensure_schema():
    insp = inspect(engine)
    tables = insp.get_table_names()
    if "reports" in tables:
        cols = [c["name"] for c in insp.get_columns("reports")]
        if "features_json" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE reports ADD COLUMN features_json TEXT DEFAULT '{}'")
                )
    if "turns" in tables:
        cols = [c["name"] for c in insp.get_columns("turns")]
        if "audio_json" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE turns ADD COLUMN audio_json TEXT DEFAULT '{}'")
                )


_ensure_schema()

app = FastAPI(title="SpeakPal API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(scenes.router)
app.include_router(sessions.router)
app.include_router(reports.router)


@app.get("/")
def root():
    return RedirectResponse(url="/docs")


@app.get("/api/health")
def health():
    return {"status": "ok"}
