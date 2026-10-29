from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings

_is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _secure_delete(dbapi_connection, _record):
        """删除时把内容覆盖成 0，而不是只标记页空闲。

        用户要求「数据全部不保留」，SQLite 默认删行后原内容还留在空闲页里，
        用十六进制工具能翻出来。开 secure_delete 后新写入会覆盖掉旧内容。
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA secure_delete=ON")
        cursor.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
