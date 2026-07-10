"""UI-independent helpers for specialist workflows that return a video URL."""

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


async def execute_digital_human_video(
    core: Any,
    task_id: str,
    mode: str,
    character_path: str,
    script: str,
    product_path: str | None,
    product_title: str | None,
    tts_inference_mode: str,
    voice: str | None,
    speed: float,
) -> str:
    """Run the digital-human workflow without any UI dependency."""
    task_dir, _ = create_task_output_dir(task_id)
    kit = await core._get_or_create_comfykit()
    narration = script.strip()

    if mode == "digital":
        if narration:
            image_workflow = "runninghub/digital_customize.json"
            image_params = {"firstimage": character_path, "secondimage": product_path}
        else:
            image_workflow = "runninghub/digital_image.json"
            image_params = {"firstimage": character_path, "secondimage": product_path, "goodstype": product_title}
        image_result = await kit.execute(
            json.loads(_resolve_workflow_path(image_workflow).read_text(encoding="utf-8"))["workflow_id"],
            image_params,
        )
        generated_image = (getattr(image_result, "images", None) or [None])[0]
        if not generated_image:
            raise RuntimeError("Digital-human image workflow did not return an image")
        if not narration:
            narration = (getattr(image_result, "texts", None) or [""])[0]
        if not narration:
            raise RuntimeError("Digital-human image workflow did not return narration text")
    else:
        generated_image = character_path

    audio_path = str(Path(task_dir) / "narration.mp3")
    await core.tts(
        text=narration,
        output_path=audio_path,
        inference_mode=tts_inference_mode,
        voice=voice,
        speed=speed,
    )
    result = await kit.execute(
        json.loads(_resolve_workflow_path("runninghub/digital_combination.json").read_text(encoding="utf-8"))["workflow_id"],
        {"videoimage": generated_image, "audio": audio_path},
    )
    final_video_path = Path(task_dir) / "final.mp4"
    timeout = httpx.Timeout(300.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("GET", _extract_video_url(result)) as response:
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
