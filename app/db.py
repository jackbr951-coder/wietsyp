import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone

PATH = os.getenv("DAFTER_DB", "dafter.db")


def _c():
    c = sqlite3.connect(PATH)
    c.execute("CREATE TABLE IF NOT EXISTS pieces (id TEXT PRIMARY KEY, created TEXT, data TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS stories (id TEXT PRIMARY KEY, audio BLOB, mime TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS photos (id TEXT PRIMARY KEY, image BLOB, mime TEXT)")
    return c


def create() -> str:
    pid = uuid.uuid4().hex[:8]
    with _c() as c:
        c.execute("INSERT INTO pieces VALUES (?,?,?)", (pid, datetime.now(timezone.utc).isoformat(), "{}"))
    return pid


def get(pid: str):
    with _c() as c:
        r = c.execute("SELECT data, created FROM pieces WHERE id=?", (pid,)).fetchone()
    if not r:
        return None
    d = json.loads(r[0])
    d["id"], d["created"] = pid, r[1]
    return d


def save(pid: str, data: dict):
    data = {k: v for k, v in data.items() if k not in ("id", "created")}
    with _c() as c:
        c.execute("UPDATE pieces SET data=? WHERE id=?", (json.dumps(data, ensure_ascii=False), pid))


def save_story(pid: str, audio: bytes, mime: str):
    with _c() as c:
        c.execute("INSERT OR REPLACE INTO stories VALUES (?,?,?)", (pid, audio, mime))


def get_story(pid: str):
    with _c() as c:
        return c.execute("SELECT audio, mime FROM stories WHERE id=?", (pid,)).fetchone()


def save_photo(pid: str, image: bytes, mime: str):
    with _c() as c:
        c.execute("INSERT OR REPLACE INTO photos VALUES (?,?,?)", (pid, image, mime))


def get_photo(pid: str):
    with _c() as c:
        return c.execute("SELECT image, mime FROM photos WHERE id=?", (pid,)).fetchone()
