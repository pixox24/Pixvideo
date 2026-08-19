"""Persistent style-slot storage for reusable reference-image styles."""

from __future__ import annotations

import json
import io
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, ImageOps

from pixelle_video.utils.os_util import get_data_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StyleSlotRepository:
    def __init__(self, db_path: str | Path | None = None, media_root: str | Path | None = None):
        self.media_root = Path(media_root or get_data_path("style-slots")).resolve()
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(db_path or get_data_path("style-slots.sqlite3"))
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS style_slots (
              id TEXT PRIMARY KEY, name TEXT NOT NULL, source_image_relative_path TEXT NOT NULL,
              thumbnail_relative_path TEXT NOT NULL, style_prefix TEXT NOT NULL,
              style_tags_json TEXT NOT NULL DEFAULT '[]', visual_features_json TEXT NOT NULL DEFAULT '{}',
              negative_constraints_json TEXT NOT NULL DEFAULT '[]', confidence REAL,
              strength INTEGER NOT NULL DEFAULT 70, source TEXT NOT NULL DEFAULT 'user_upload',
              locked INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )"""
        )
        self.connection.commit()

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"], "name": row["name"],
            "sourceImageUrl": f"/api/style-slots/{row['id']}/image",
            "thumbnailUrl": f"/api/style-slots/{row['id']}/image",
            "stylePrefix": row["style_prefix"],
            "styleTags": json.loads(row["style_tags_json"] or "[]"),
            "visualFeatures": json.loads(row["visual_features_json"] or "{}"),
            "negativeConstraints": json.loads(row["negative_constraints_json"] or "[]"),
            "confidence": row["confidence"], "strength": row["strength"],
            "source": row["source"], "locked": bool(row["locked"]),
            "createdAt": row["created_at"], "updatedAt": row["updated_at"],
        }

    def list(self) -> list[dict[str, Any]]:
        return [self._decode(row) for row in self.connection.execute("SELECT * FROM style_slots ORDER BY created_at").fetchall()]

    def get(self, slot_id: str) -> dict[str, Any] | None:
        row = self.connection.execute("SELECT * FROM style_slots WHERE id=?", (slot_id,)).fetchone()
        return self._decode(row) if row else None

    def create(self, *, name: str, image_bytes: bytes, style: dict[str, Any], strength: int = 70) -> dict[str, Any]:
        if self.connection.execute("SELECT COUNT(*) FROM style_slots").fetchone()[0] >= 12:
            raise ValueError("style_slot_limit_reached")
        slot_id = f"style_{uuid4().hex[:12]}"
        folder = self.media_root / slot_id
        folder.mkdir(parents=True, exist_ok=False)
        try:
            image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
            image_path = folder / "reference.jpg"
            image_path.write_bytes(output.getvalue())
        except Exception as exc:
            folder.rmdir()
            raise ValueError("vision_image_invalid") from exc
        now = _now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO style_slots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (slot_id, (name or style.get("style_name") or "未命名画风").strip()[:80],
                 f"data/style-slots/{slot_id}/reference.jpg", f"data/style-slots/{slot_id}/reference.jpg",
                 style["style_prefix"], json.dumps(style.get("style_tags", []), ensure_ascii=False),
                 json.dumps(style.get("visual_features", {}), ensure_ascii=False),
                 json.dumps(style.get("negative_constraints", []), ensure_ascii=False),
                 float(style.get("confidence") or 0), max(0, min(100, int(strength))), "user_upload", 0, now, now),
            )
        return self.get(slot_id) or {}

    def update(self, slot_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get(slot_id)
        if not current:
            return None
        fields: list[str] = []
        params: list[Any] = []
        mapping = {"name": "name", "stylePrefix": "style_prefix", "styleTags": "style_tags_json", "visualFeatures": "visual_features_json", "negativeConstraints": "negative_constraints_json", "strength": "strength", "locked": "locked"}
        for key, column in mapping.items():
            if key not in values:
                continue
            value = values[key]
            if key in {"styleTags", "visualFeatures", "negativeConstraints"}:
                value = json.dumps(value, ensure_ascii=False)
            if key == "stylePrefix" and not str(value or "").strip():
                raise ValueError("style_prefix_empty")
            fields.append(f"{column}=?"); params.append(value)
        if not fields:
            return current
        fields.append("updated_at=?"); params.extend([_now(), slot_id])
        with self.connection:
            self.connection.execute(f"UPDATE style_slots SET {', '.join(fields)} WHERE id=?", params)
        return self.get(slot_id)

    def delete(self, slot_id: str) -> bool:
        current = self.get(slot_id)
        if not current:
            return False
        with self.connection:
            self.connection.execute("DELETE FROM style_slots WHERE id=?", (slot_id,))
        folder = self.media_root / slot_id
        for path in folder.glob("*") if folder.exists() else []:
            path.unlink(missing_ok=True)
        folder.rmdir() if folder.exists() else None
        return True
