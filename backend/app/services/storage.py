"""数据位置：当前库路径、写 data_location.json、复制库文件。

只写配置、不热切换：SQLite 的 engine 在 import 时就绑定了库文件，
运行中换库会留下半开连接（旧 inode 还在，新连接建出空库、表都没有）。
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

from ..config import LOCATION_FILE, settings

DB_FILENAME = "speakpal.db"
_SQLITE_PREFIX = "sqlite:///"


def current_db_path() -> Path:
    """settings.database_url → 绝对路径。相对路径按进程 CWD 解析（与 engine 行为一致）。"""
    url = (settings.database_url or "").strip()
    if url.startswith(_SQLITE_PREFIX):
        raw = url[len(_SQLITE_PREFIX) :].strip()
        if raw and raw != ":memory:":
            return Path(raw).expanduser().resolve()
    return (LOCATION_FILE.parent / DB_FILENAME).resolve()


def storage_info() -> dict:
    path = current_db_path()
    exists = path.exists()
    parent = path.parent
    return {
        "path": str(path),
        "data_dir": str(parent),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else None,
        "writable": parent.exists() and os.access(parent, os.W_OK),
        "source": settings.database_source,
        "env_override": settings.database_source == "env",
        "location_file": str(LOCATION_FILE),
    }


def normalize_target(raw: str) -> Path:
    """收目录或 .db 文件，统一成库文件绝对路径。"""
    text = str(raw or "").strip().strip('"').strip("'")
    if not text:
        raise ValueError("路径为空")
    target = Path(text).expanduser()
    if target.suffix.lower() != ".db":
        target = target / DB_FILENAME
    return target.resolve()


def copy_current_to(target: Path) -> int:
    """把当前库复制到目标位置（复制不是移动，旧库原位不动）；返回复制的字节数。"""
    source = current_db_path()
    if not source.exists() or source == target:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target.stat().st_size


def write_location(target: Path) -> dict:
    data = {
        "database_url": f"{_SQLITE_PREFIX}{target.as_posix()}",
        "db_path": str(target),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    LOCATION_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return data
