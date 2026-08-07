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
    GenerationPhase,
    GenerationRun,
    GenerationRunItem,
    GenerationRunItemStatus,
    GenerationRunStatus,
    GenerationStatus,
    Project,
    Scene,
    utc_now,
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
              status TEXT NOT NULL DEFAULT 'pending', updated_at TEXT NOT NULL,
              image_fingerprint TEXT, audio_fingerprint TEXT, UNIQUE(project_id, position)
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
            CREATE TABLE IF NOT EXISTS generation_runs (
              run_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
              task_id TEXT NOT NULL UNIQUE, status TEXT NOT NULL,
              parameter_snapshot_json TEXT NOT NULL, current_scene_id TEXT,
              total_count INTEGER NOT NULL DEFAULT 0,
              completed_count INTEGER NOT NULL DEFAULT 0,
              skipped_count INTEGER NOT NULL DEFAULT 0,
              failed_count INTEGER NOT NULL DEFAULT 0,
              candidate_review_count INTEGER NOT NULL DEFAULT 0,
              pause_requested INTEGER NOT NULL DEFAULT 0,
              cancel_requested INTEGER NOT NULL DEFAULT 0,
              error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS generation_run_items (
              item_id TEXT PRIMARY KEY,
              run_id TEXT NOT NULL REFERENCES generation_runs(run_id) ON DELETE CASCADE,
              scene_id TEXT NOT NULL REFERENCES scenes(scene_id) ON DELETE CASCADE,
              position INTEGER NOT NULL, narration_snapshot TEXT NOT NULL,
              prompt_snapshot TEXT NOT NULL, narration_fingerprint TEXT NOT NULL,
              image_fingerprint TEXT NOT NULL, tts_status TEXT NOT NULL,
              image_status TEXT NOT NULL, status TEXT NOT NULL, skip_reason TEXT,
              candidate_version_id TEXT, error TEXT, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL, UNIQUE(run_id, scene_id)
            );
            CREATE INDEX IF NOT EXISTS idx_generation_runs_project_status
              ON generation_runs(project_id, status);
            CREATE INDEX IF NOT EXISTS idx_generation_run_items_run_position
              ON generation_run_items(run_id, position);
            """
        )
        self._ensure_column("scenes", "image_fingerprint", "TEXT")
        self._ensure_column("scenes", "audio_fingerprint", "TEXT")
        self._connection.commit()

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in self._connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
            """
            INSERT INTO scenes (
              scene_id, project_id, position, narration, visual_prompt,
              current_version_id, audio_relative_path, subtitle_alignment_json,
              duration_seconds, manual_hold_seconds, duration_mode, status,
              updated_at, image_fingerprint, audio_fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (scene.scene_id, scene.project_id, scene.position, scene.narration, scene.visual_prompt,
             scene.current_version_id, scene.audio_relative_path, _json(scene.subtitle_alignment),
             scene.duration_seconds, scene.manual_hold_seconds, scene.duration_mode, scene.status,
             _dt(scene.updated_at), scene.image_fingerprint, scene.audio_fingerprint),
        )

    def get_project(self, project_id: str) -> Project | None:
        row = self._connection.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            return None
        return Project(row["title"], json.loads(row["config_json"]), row["project_id"], row["source"],
                       row["source_history_task_id"], _from_dt(row["created_at"]), _from_dt(row["updated_at"]))

    def get_project_by_source_history_task_id(self, task_id: str) -> Project | None:
        row = self._connection.execute("SELECT project_id FROM projects WHERE source_history_task_id=?", (task_id,)).fetchone()
        return self.get_project(row["project_id"]) if row else None

    def get_scene(self, scene_id: str) -> Scene | None:
        row = self._connection.execute("SELECT * FROM scenes WHERE scene_id=?", (scene_id,)).fetchone()
        return self._scene_from_row(row) if row else None

    def list_project_scenes(self, project_id: str) -> list[Scene]:
        rows = self._connection.execute("SELECT * FROM scenes WHERE project_id=? ORDER BY position", (project_id,)).fetchall()
        return [self._scene_from_row(row) for row in rows]

    @staticmethod
    def _scene_from_row(row: sqlite3.Row) -> Scene:
        return Scene(
            project_id=row["project_id"],
            position=row["position"],
            narration=row["narration"],
            visual_prompt=row["visual_prompt"],
            scene_id=row["scene_id"],
            current_version_id=row["current_version_id"],
            audio_relative_path=row["audio_relative_path"],
            subtitle_alignment=json.loads(row["subtitle_alignment_json"]),
            duration_seconds=row["duration_seconds"],
            manual_hold_seconds=row["manual_hold_seconds"],
            duration_mode=row["duration_mode"],
            status=row["status"],
            updated_at=_from_dt(row["updated_at"]),
            image_fingerprint=row["image_fingerprint"],
            audio_fingerprint=row["audio_fingerprint"],
        )

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
        allowed = {"position", "narration", "visual_prompt", "current_version_id", "audio_relative_path", "subtitle_alignment", "duration_seconds", "manual_hold_seconds", "duration_mode", "status", "updated_at", "image_fingerprint", "audio_fingerprint"}
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
            query += " AND scene_id=?"
            args.append(scene_id)
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
        if not row:
            return None
        return self._generation_job_from_row(row)

    @staticmethod
    def _generation_job_from_row(row: sqlite3.Row) -> GenerationJob:
        return GenerationJob(row["project_id"], GenerationKind(row["kind"]), row["task_id"], json.loads(row["request_snapshot_json"]), row["scene_id"], row["job_id"], GenerationStatus(row["status"]), row["progress"], row["error"], _from_dt(row["created_at"]), _from_dt(row["updated_at"]))

    def list_generation_jobs(
        self,
        project_id: str,
        include_terminal: bool = True,
    ) -> list[GenerationJob]:
        query = "SELECT * FROM generation_jobs WHERE project_id=?"
        args: list[Any] = [project_id]
        if not include_terminal:
            query += " AND status NOT IN (?, ?, ?)"
            args.extend([
                GenerationStatus.COMPLETED.value,
                GenerationStatus.FAILED.value,
                GenerationStatus.CANCELLED.value,
            ])
        rows = self._connection.execute(query + " ORDER BY created_at DESC", args).fetchall()
        return [self._generation_job_from_row(row) for row in rows]

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
        allowed = {"status", "progress", "error", "updated_at"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if "status" in values:
            values["status"] = values["status"].value if isinstance(values["status"], GenerationStatus) else values["status"]
        if "updated_at" in values:
            values["updated_at"] = _dt(values["updated_at"])
        if not values:
            return
        with self._connection:
            self._connection.execute(f"UPDATE generation_jobs SET {', '.join(f'{k}=?' for k in values)} WHERE job_id=?", (*values.values(), job_id))

    def create_generation_run(
        self,
        run: GenerationRun,
        items: list[GenerationRunItem],
    ) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO generation_runs (
                  run_id, project_id, task_id, status, parameter_snapshot_json,
                  current_scene_id, total_count, completed_count, skipped_count,
                  failed_count, candidate_review_count, pause_requested,
                  cancel_requested, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.project_id,
                    run.task_id,
                    run.status.value,
                    _json(run.parameter_snapshot),
                    run.current_scene_id,
                    run.total_count,
                    run.completed_count,
                    run.skipped_count,
                    run.failed_count,
                    run.candidate_review_count,
                    int(run.pause_requested),
                    int(run.cancel_requested),
                    run.error,
                    _dt(run.created_at),
                    _dt(run.updated_at),
                ),
            )
            for item in items:
                self._insert_generation_run_item(item)

    def _insert_generation_run_item(self, item: GenerationRunItem) -> None:
        self._connection.execute(
            """
            INSERT INTO generation_run_items (
              item_id, run_id, scene_id, position, narration_snapshot,
              prompt_snapshot, narration_fingerprint, image_fingerprint,
              tts_status, image_status, status, skip_reason,
              candidate_version_id, error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.item_id,
                item.run_id,
                item.scene_id,
                item.position,
                item.narration_snapshot,
                item.prompt_snapshot,
                item.narration_fingerprint,
                item.image_fingerprint,
                item.tts_status.value,
                item.image_status.value,
                item.status.value,
                item.skip_reason,
                item.candidate_version_id,
                item.error,
                _dt(item.created_at),
                _dt(item.updated_at),
            ),
        )

    def get_generation_run(self, run_id: str) -> GenerationRun | None:
        row = self._connection.execute(
            "SELECT * FROM generation_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        return self._generation_run_from_row(row) if row else None

    @staticmethod
    def _generation_run_from_row(row: sqlite3.Row) -> GenerationRun:
        return GenerationRun(
            project_id=row["project_id"],
            task_id=row["task_id"],
            parameter_snapshot=json.loads(row["parameter_snapshot_json"]),
            run_id=row["run_id"],
            status=GenerationRunStatus(row["status"]),
            current_scene_id=row["current_scene_id"],
            total_count=row["total_count"],
            completed_count=row["completed_count"],
            skipped_count=row["skipped_count"],
            failed_count=row["failed_count"],
            candidate_review_count=row["candidate_review_count"],
            pause_requested=bool(row["pause_requested"]),
            cancel_requested=bool(row["cancel_requested"]),
            error=row["error"],
            created_at=_from_dt(row["created_at"]),
            updated_at=_from_dt(row["updated_at"]),
        )

    def get_active_generation_run(self, project_id: str) -> GenerationRun | None:
        terminal = (
            GenerationRunStatus.COMPLETED.value,
            GenerationRunStatus.COMPLETED_WITH_FAILURES.value,
            GenerationRunStatus.CANCELLED.value,
            GenerationRunStatus.FAILED.value,
        )
        row = self._connection.execute(
            """
            SELECT * FROM generation_runs
            WHERE project_id=? AND status NOT IN (?, ?, ?, ?)
            ORDER BY created_at DESC LIMIT 1
            """,
            (project_id, *terminal),
        ).fetchone()
        return self._generation_run_from_row(row) if row else None

    def list_generation_runs(self, project_id: str, limit: int = 20) -> list[GenerationRun]:
        rows = self._connection.execute(
            """
            SELECT * FROM generation_runs
            WHERE project_id=? ORDER BY created_at DESC LIMIT ?
            """,
            (project_id, max(1, int(limit))),
        ).fetchall()
        return [self._generation_run_from_row(row) for row in rows]

    def get_generation_run_item(self, item_id: str) -> GenerationRunItem | None:
        row = self._connection.execute(
            "SELECT * FROM generation_run_items WHERE item_id=?",
            (item_id,),
        ).fetchone()
        return self._generation_run_item_from_row(row) if row else None

    def list_generation_run_items(self, run_id: str) -> list[GenerationRunItem]:
        rows = self._connection.execute(
            """
            SELECT * FROM generation_run_items
            WHERE run_id=? ORDER BY position
            """,
            (run_id,),
        ).fetchall()
        return [self._generation_run_item_from_row(row) for row in rows]

    @staticmethod
    def _generation_run_item_from_row(row: sqlite3.Row) -> GenerationRunItem:
        return GenerationRunItem(
            run_id=row["run_id"],
            scene_id=row["scene_id"],
            position=row["position"],
            narration_snapshot=row["narration_snapshot"],
            prompt_snapshot=row["prompt_snapshot"],
            narration_fingerprint=row["narration_fingerprint"],
            image_fingerprint=row["image_fingerprint"],
            item_id=row["item_id"],
            tts_status=GenerationPhase(row["tts_status"]),
            image_status=GenerationPhase(row["image_status"]),
            status=GenerationRunItemStatus(row["status"]),
            skip_reason=row["skip_reason"],
            candidate_version_id=row["candidate_version_id"],
            error=row["error"],
            created_at=_from_dt(row["created_at"]),
            updated_at=_from_dt(row["updated_at"]),
        )

    def update_generation_run(self, run_id: str, **changes: Any) -> None:
        allowed = {
            "status",
            "parameter_snapshot",
            "current_scene_id",
            "total_count",
            "completed_count",
            "skipped_count",
            "failed_count",
            "candidate_review_count",
            "pause_requested",
            "cancel_requested",
            "error",
            "updated_at",
        }
        values = {key: value for key, value in changes.items() if key in allowed}
        if not values:
            return
        if "status" in values:
            status = values["status"]
            values["status"] = status.value if isinstance(status, GenerationRunStatus) else status
        if "parameter_snapshot" in values:
            values["parameter_snapshot_json"] = _json(values.pop("parameter_snapshot"))
        for name in ("pause_requested", "cancel_requested"):
            if name in values:
                values[name] = int(bool(values[name]))
        values["updated_at"] = _dt(values.get("updated_at", utc_now()))
        with self._connection:
            self._connection.execute(
                f"UPDATE generation_runs SET {', '.join(f'{key}=?' for key in values)} WHERE run_id=?",
                (*values.values(), run_id),
            )

    def update_generation_run_item(self, item_id: str, **changes: Any) -> None:
        allowed = {
            "tts_status",
            "image_status",
            "status",
            "skip_reason",
            "candidate_version_id",
            "error",
            "updated_at",
        }
        values = {key: value for key, value in changes.items() if key in allowed}
        if not values:
            return
        for name in ("tts_status", "image_status"):
            if name in values and isinstance(values[name], GenerationPhase):
                values[name] = values[name].value
        if "status" in values and isinstance(values["status"], GenerationRunItemStatus):
            values["status"] = values["status"].value
        values["updated_at"] = _dt(values.get("updated_at", utc_now()))
        with self._connection:
            self._connection.execute(
                f"UPDATE generation_run_items SET {', '.join(f'{key}=?' for key in values)} WHERE item_id=?",
                (*values.values(), item_id),
            )

    def mark_remaining_run_items_cancelled(self, run_id: str) -> None:
        timestamp = _dt(utc_now())
        with self._connection:
            self._connection.execute(
                """
                UPDATE generation_run_items
                SET status=?,
                    tts_status=CASE WHEN tts_status=? THEN ? ELSE tts_status END,
                    image_status=CASE WHEN image_status=? THEN ? ELSE image_status END,
                    updated_at=?
                WHERE run_id=? AND status=?
                """,
                (
                    GenerationRunItemStatus.CANCELLED.value,
                    GenerationPhase.PENDING.value,
                    GenerationPhase.CANCELLED.value,
                    GenerationPhase.PENDING.value,
                    GenerationPhase.CANCELLED.value,
                    timestamp,
                    run_id,
                    GenerationRunItemStatus.QUEUED.value,
                ),
            )

    def recompute_generation_run_counts(self, run_id: str) -> GenerationRun:
        row = self._connection.execute(
            """
            SELECT
              SUM(CASE WHEN status=? THEN 1 ELSE 0 END) AS completed_count,
              SUM(CASE WHEN status=? THEN 1 ELSE 0 END) AS skipped_count,
              SUM(CASE WHEN status=? THEN 1 ELSE 0 END) AS failed_count,
              SUM(CASE WHEN status=? THEN 1 ELSE 0 END) AS candidate_review_count
            FROM generation_run_items WHERE run_id=?
            """,
            (
                GenerationRunItemStatus.COMPLETED.value,
                GenerationRunItemStatus.SKIPPED.value,
                GenerationRunItemStatus.FAILED.value,
                GenerationRunItemStatus.CANDIDATE_REVIEW.value,
                run_id,
            ),
        ).fetchone()
        timestamp = _dt(utc_now())
        with self._connection:
            self._connection.execute(
                """
                UPDATE generation_runs
                SET completed_count=?, skipped_count=?, failed_count=?,
                    candidate_review_count=?, updated_at=?
                WHERE run_id=?
                """,
                (
                    row["completed_count"] or 0,
                    row["skipped_count"] or 0,
                    row["failed_count"] or 0,
                    row["candidate_review_count"] or 0,
                    timestamp,
                    run_id,
                ),
            )
        run = self.get_generation_run(run_id)
        if run is None:
            raise ValueError("generation run not found")
        return run

    def create_export_revision(self, revision: ExportRevision) -> None:
        with self._connection:
            self._connection.execute("INSERT INTO export_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (revision.export_id, revision.project_id, _json(revision.snapshot), revision.output_relative_path, revision.status.value, revision.error, _dt(revision.created_at), _dt(revision.updated_at)))

    def update_export_revision(self, export_id: str, **changes: Any) -> None:
        allowed = {"output_relative_path", "status", "error", "updated_at"}
        values = {key: value for key, value in changes.items() if key in allowed}
        if "status" in values:
            values["status"] = values["status"].value if isinstance(values["status"], GenerationStatus) else values["status"]
        if "updated_at" in values:
            values["updated_at"] = _dt(values["updated_at"])
        if not values:
            return
        with self._connection:
            self._connection.execute(f"UPDATE export_revisions SET {', '.join(f'{k}=?' for k in values)} WHERE export_id=?", (*values.values(), export_id))

    def get_export_revision(self, export_id: str) -> ExportRevision | None:
        row = self._connection.execute("SELECT * FROM export_revisions WHERE export_id=?", (export_id,)).fetchone()
        if not row:
            return None
        return ExportRevision(row["project_id"], json.loads(row["snapshot_json"]), row["export_id"], row["output_relative_path"], GenerationStatus(row["status"]), row["error"], _from_dt(row["created_at"]), _from_dt(row["updated_at"]))

    def close(self) -> None:
        self._connection.close()
