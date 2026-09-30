"""Speichert Entwürfe und Fotos lokal (SQLite + Ordner data/photos)."""

import json
import sqlite3
import time
from pathlib import Path

from .config import DATA_DIR


class Storage:
    def __init__(self, data_dir: Path = DATA_DIR):
        self.photo_dir = data_dir / "photos"
        self.photo_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(data_dir / "karten.db")
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'offen',
                data TEXT NOT NULL,
                created REAL NOT NULL
            )"""
        )
        self.db.commit()

    def create(self, chat_id: int, data: dict, photos: list[bytes]) -> int:
        cur = self.db.execute(
            "INSERT INTO drafts (chat_id, data, created) VALUES (?, ?, ?)",
            (chat_id, "{}", time.time()),
        )
        draft_id = cur.lastrowid
        paths = []
        for i, img in enumerate(photos):
            path = self.photo_dir / f"{draft_id}_{i}.jpg"
            path.write_bytes(img)
            paths.append(str(path))
        data["photos"] = paths
        data["sku"] = f"KARTE-{draft_id}-{int(time.time())}"
        self.db.execute("UPDATE drafts SET data = ? WHERE id = ?", (json.dumps(data), draft_id))
        self.db.commit()
        return draft_id

    def get(self, draft_id: int) -> dict | None:
        row = self.db.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if not row:
            return None
        data = json.loads(row["data"])
        data.update(id=row["id"], chat_id=row["chat_id"], status=row["status"])
        return data

    def update(self, draft_id: int, data: dict, status: str | None = None) -> None:
        clean = {k: v for k, v in data.items() if k not in ("id", "chat_id", "status")}
        self.db.execute("UPDATE drafts SET data = ? WHERE id = ?", (json.dumps(clean), draft_id))
        if status:
            self.db.execute("UPDATE drafts SET status = ? WHERE id = ?", (status, draft_id))
        self.db.commit()

    def by_status(self, chat_id: int, status: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT id FROM drafts WHERE chat_id = ? AND status = ? ORDER BY id", (chat_id, status)
        ).fetchall()
        return [self.get(r["id"]) for r in rows]

    def photos(self, draft: dict) -> list[bytes]:
        return [Path(p).read_bytes() for p in draft.get("photos", [])]
