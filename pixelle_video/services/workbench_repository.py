"""SQLite persistence for editable AI video workbench projects."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pixelle_video.models.workbench import (
    AssetSource,
    AssetVersion,
    ExportRevision,
    GenerationJob,
    GenerationKind,
    GenerationStatus,
    Project,
    Scene,
)


def _dt(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _from_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return (parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed).astimezone(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class WorkbenchRepository:
    def __init__(self, db_path: str | Path):
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
              project_id TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL,
              source_history_task_id TEXT UNIQUE, config_json TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scenes (
              scene_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
              position INTEGER NOT NULL, narration TEXT NOT NULL, visual_prompt TEXT NOT NULL DEFAULT '',
              current_version_id TEXT, audio_relative_path TEXT,
              subtitle_alignment_json TEXT NOT NULL DEFAULT '[]', duration_seconds REAL NOT NULL DEFAULT 0,
              manual_hold_seconds REAL NOT NULL DEFAULT 0, duration_mode TEXT NOT NULL DEFAULT 'audio',
              status TEXT NOT NULL DEFAULT 'pending', updated_at TEXT NOT NULL, UNIQUE(project_id, position)
            );
            CREATE TABLE IF NOT EXISTS asset_versions (
              version_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
              scene_id TEXT REFERENCES scenes(scene_id) ON DELETE CASCADE, source TEXT NOT NULL,
              relative_path TEXT NOT NULL, thumbnail_relative_path TEXT, prompt_snapshot TEXT,
              parameters_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS generation_jobs (
              job_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
              scene_id TEXT REFERENCES scenes(scene_id) ON DELETE SET NULL, kind TEXT NOT NULL,
              task_id TEXT NOT NULL UNIQUE, request_snapshot_json TEXT NOT NULL, status TEXT NOT NULL,
              progress REAL NOT NULL DEFAULT 0, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS export_revisions (
              export_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
              snapshot_json TEXT NOT NULL, output_relative_path TEXT, status TEXT NOT NULL,
              error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    def table_names(self) -> set[str]:
        rows = self._connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {row[0] for row in rows}

    def create_project(self, project: Project, scenes: list[Scene]) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
                (project.project_id, project.title, project.source, project.source_history_task_id,
                 _json(project.config), _dt(project.created_at), _dt(project.updated_at)),
            )
            for scene in scenes:
                self._insert_scene(scene)

    def _insert_scene(self, scene: Scene) -> None:
        self._connection.execute(
            "INSERT INTO scenes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (scene.scene_id, scene.project_id, scene.position, scene.narration, scene.visual_prompt,
             scene.current_version_id, scene.audio_relative_path, _json(scene.subtitle_alignment),
             scene.duration_seconds, scene.manual_hold_seconds, scene.duration_mode, scene.status, _dt(scene.updated_at),),
        )

    def get_project(self, project_id: str) -> Project | None:
        row = self._connection.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            return None
        return Project(row["title"], json.loads(row["config_json"]), row["project_id"], row["source"],
                       row["source_history_task_id"], _from_dt(row["created_at"]), _from_dt(row["updated_at"]))

    def get_scene(self, scene_id: str) -> Scene | None:
        row = self._connection.execute("SELECT * FROM scenes WHERE scene_id=?", (scene_id,)).fetchone()
        return self._scene_from_row(row) if row else None

    def list_project_scenes(self, project_id: str) -> list[Scene]:
        rows = self._connection.execute("SELECT * FROM scenes WHERE project_id=? ORDER BY position", (project_id,)).fetchall()
        return [self._scene_from_row(row) for row in rows]

    @staticmethod
    def _scene_from_row(row: sqlite3.Row) -> Scene:
        return Scene(row["project_id"], row["position"], row["narration"], row["visual_prompt"], row["scene_id"],
                     row["current_version_id"], row["audio_relative_path"], json.loads(row["subtitle_alignment_json"]),
                     row["duration_seconds"], row["manual_hold_seconds"], row["duration_mode"], row["status"], _from_dt(row["updated_at"]))

    def update_project(self, project_id: str, **changes: Any) -> None:
        allowed = {"title", "source", "source_history_task_id", "config", "updated_at"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if "config" in values:
            values["config_json"] = _json(values.pop("config"))
        if "updated_at" in values:
            values["updated_at"] = _dt(values["updated_at"])
        if not values:
            return
        with self._connection:
            self._connection.execute(f"UPDATE projects SET {', '.join(f'{k}=?' for k in values)} WHERE project_id=?", (*values.values(), project_id))

    def update_scene(self, scene_id: str, **changes: Any) -> None:
        allowed = {"position", "narration", "visual_prompt", "current_version_id", "audio_relative_path", "subtitle_alignment", "duration_seconds", "manual_hold_seconds", "duration_mode", "status", "updated_at"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if "subtitle_alignment" in values:
            values["subtitle_alignment_json"] = _json(values.pop("subtitle_alignment"))
        if "updated_at" in values:
            values["updated_at"] = _dt(values["updated_at"])
        if not values:
            return
        with self._connection:
            self._connection.execute(f"UPDATE scenes SET {', '.join(f'{k}=?' for k in values)} WHERE scene_id=?", (*values.values(), scene_id))

    def reorder_scenes(self, project_id: str, scene_ids: list[str]) -> None:
        with self._connection:
            for position, scene_id in enumerate(scene_ids):
                self._connection.execute("UPDATE scenes SET position=? WHERE scene_id=? AND project_id=?", (position + len(scene_ids), scene_id, project_id))
            for position, scene_id in enumerate(scene_ids):
                self._connection.execute("UPDATE scenes SET position=? WHERE scene_id=? AND project_id=?", (position, scene_id, project_id))

    def create_asset_version(self, version: AssetVersion) -> None:
        with self._connection:
            self._connection.execute("INSERT INTO asset_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (version.version_id, version.project_id, version.scene_id, version.source.value, version.relative_path,
                 version.thumbnail_relative_path, version.prompt_snapshot, _json(version.parameters), _dt(version.created_at)))

    def get_asset_version(self, version_id: str) -> AssetVersion | None:
        row = self._connection.execute("SELECT * FROM asset_versions WHERE version_id=?", (version_id,)).fetchone()
        return self._asset_from_row(row) if row else None

    get_asset = get_asset_version

    def list_asset_versions(self, project_id: str, scene_id: str | None = None) -> list[AssetVersion]:
        query, args = "SELECT * FROM asset_versions WHERE project_id=?", [project_id]
        if scene_id is not None:
            query += " AND scene_id=?"; args.append(scene_id)
        rows = self._connection.execute(query + " ORDER BY created_at", args).fetchall()
        return [self._asset_from_row(row) for row in rows]

    @staticmethod
    def _asset_from_row(row: sqlite3.Row) -> AssetVersion:
        return AssetVersion(row["project_id"], row["scene_id"], AssetSource(row["source"]), row["relative_path"], row["prompt_snapshot"], row["version_id"], row["thumbnail_relative_path"], json.loads(row["parameters_json"]), _from_dt(row["created_at"]))

    def select_asset_version(self, project_id: str, scene_id: str, version_id: str) -> None:
        with self._connection:
            exists = self._connection.execute("SELECT 1 FROM asset_versions WHERE version_id=? AND project_id=? AND scene_id=?", (version_id, project_id, scene_id)).fetchone()
            if not exists:
                raise ValueError("asset version does not belong to scene")
            self._connection.execute("UPDATE scenes SET current_version_id=? WHERE scene_id=? AND project_id=?", (version_id, scene_id, project_id))

    def create_generation_job(self, job: GenerationJob) -> None:
        with self._connection:
            self._connection.execute("INSERT INTO generation_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (job.job_id, job.project_id, job.scene_id, job.kind.value, job.task_id, _json(job.request_snapshot), job.status.value, job.progress, job.error, _dt(job.created_at), _dt(job.updated_at)))

    def get_generation_job(self, job_id: str) -> GenerationJob | None:
        row = self._connection.execute("SELECT * FROM generation_jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row: return None
        return GenerationJob(row["project_id"], GenerationKind(row["kind"]), row["task_id"], json.loads(row["request_snapshot_json"]), row["scene_id"], row["job_id"], GenerationStatus(row["status"]), row["progress"], row["error"], _from_dt(row["created_at"]), _from_dt(row["updated_at"]))

    def get_generation_job_by_task_id(self, task_id: str) -> GenerationJob | None:
        row = self._connection.execute("SELECT * FROM generation_jobs WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            return None
        return self.get_generation_job(row["job_id"])

    def update_generation_job_by_task_id(self, task_id: str, **changes: Any) -> None:
        job = self.get_generation_job_by_task_id(task_id)
        if job:
            self.update_generation_job(job.job_id, **changes)

    def update_generation_job(self, job_id: str, **changes: Any) -> None:
        allowed = {"status", "progress", "error", "updated_at"}; values = {k:v for k,v in changes.items() if k in allowed}
        if "status" in values: values["status"] = values["status"].value if isinstance(values["status"], GenerationStatus) else values["status"]
        if "updated_at" in values: values["updated_at"] = _dt(values["updated_at"])
        if not values: return
        with self._connection:
            self._connection.execute(f"UPDATE generation_jobs SET {', '.join(f'{k}=?' for k in values)} WHERE job_id=?", (*values.values(), job_id))

    def create_export_revision(self, revision: ExportRevision) -> None:
        with self._connection:
            self._connection.execute("INSERT INTO export_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (revision.export_id, revision.project_id, _json(revision.snapshot), revision.output_relative_path, revision.status.value, revision.error, _dt(revision.created_at), _dt(revision.updated_at)))

    def update_export_revision(self, export_id: str, **changes: Any) -> None:
        allowed = {"output_relative_path", "status", "error", "updated_at"}; values = {k:v for k,v in changes.items() if k in allowed}
        if "status" in values: values["status"] = values["status"].value if isinstance(values["status"], GenerationStatus) else values["status"]
        if "updated_at" in values: values["updated_at"] = _dt(values["updated_at"])
        if not values: return
        with self._connection:
            self._connection.execute(f"UPDATE export_revisions SET {', '.join(f'{k}=?' for k in values)} WHERE export_id=?", (*values.values(), export_id))

    def close(self) -> None:
        self._connection.close()
