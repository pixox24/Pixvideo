"""UI-independent helpers for image-to-video workflows."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import httpx

from pixelle_video.utils.os_util import create_task_output_dir, get_resource_path


def _resolve_workflow_path(workflow_key: str) -> Path:
    key = PurePosixPath(workflow_key)
    if key.is_absolute() or ".." in key.parts or key.suffix != ".json" or len(key.parts) < 2:
        raise ValueError("Invalid specialist workflow key")
    return Path(get_resource_path("workflows", *key.parts))


def _extract_video_url(result: Any) -> str:
    if getattr(result, "videos", None):
        return result.videos[0]
    for node_output in (getattr(result, "outputs", None) or {}).values():
        if isinstance(node_output, dict) and node_output.get("videos"):
            return node_output["videos"][0]
    raise RuntimeError("The workflow did not return a video")


async def execute_video_workflow(
    core: Any,
    workflow_key: str,
    workflow_params: dict[str, Any],
    task_id: str,
) -> str:
    """Execute a configured workflow and store its downloaded final video."""
    task_dir, _ = create_task_output_dir(task_id)
    workflow_path = _resolve_workflow_path(workflow_key)
    with workflow_path.open("r", encoding="utf-8") as workflow_file:
        workflow_config = json.load(workflow_file)

    kit = await core._get_or_create_comfykit()
    workflow_input = workflow_config.get("workflow_id") if workflow_config.get("source") == "runninghub" else str(workflow_path)
    if not workflow_input:
        raise ValueError(f"Workflow {workflow_key} does not define a workflow_id")

    result = await kit.execute(workflow_input, workflow_params)
    video_url = _extract_video_url(result)
    final_video_path = Path(task_dir) / "final.mp4"
    timeout = httpx.Timeout(300.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("GET", video_url) as response:
            response.raise_for_status()
            with final_video_path.open("wb") as target:
                async for chunk in response.aiter_bytes():
                    target.write(chunk)
    return str(final_video_path)


async def persist_specialist_video(
    core: Any,
    task_id: str,
    pipeline: str,
    input_params: dict[str, Any],
    final_video_path: str | None = None,
    error: str | None = None,
) -> None:
    """Persist specialist task state so the shared history UI can display it."""
    if not core.persistence:
        return

    video_path = Path(final_video_path) if final_video_path else None
    file_size = video_path.stat().st_size if video_path and video_path.exists() else 0
    duration = 0.0
    if video_path and video_path.exists() and getattr(core, "video", None):
        try:
            duration = core.video._get_video_duration(str(video_path))
        except Exception:
            duration = 0.0

    now = datetime.now().isoformat()
    await core.persistence.save_task_metadata(
        task_id,
        {
            "task_id": task_id,
            "created_at": now,
            "completed_at": now,
            "status": "failed" if error else "completed",
            "error": error,
            "input": {"pipeline": pipeline, **input_params},
            "result": {
                "video_path": final_video_path,
                "duration": duration,
                "file_size": file_size,
                "n_frames": 1,
            },
        },
    )
