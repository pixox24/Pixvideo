# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""Persisted generation history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.routers.video import path_to_url
from pixelle_video.models.progress import ProgressEvent

router = APIRouter(prefix="/history", tags=["History"])


def _add_video_url(request: Request, task: dict) -> dict:
    task = dict(task)
    video_path = task.get("video_path")
    if video_path:
        task["video_url"] = path_to_url(request, video_path)
    return task


@router.get("")
async def list_history(
    pixelle_video: PixelleVideoDep,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
):
    """List persisted generated tasks."""
    try:
        result = await pixelle_video.history.get_task_list(
            page=page,
            page_size=page_size,
            status=status,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        result["tasks"] = [_add_video_url(request, task) for task in result.get("tasks", [])]
        result["success"] = True
        return result
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{task_id}")
async def get_history_detail(
    task_id: str,
    pixelle_video: PixelleVideoDep,
    request: Request,
):
    """Return persisted task metadata and storyboard."""
    try:
        detail = await pixelle_video.history.get_task_detail(task_id)
        if not detail:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        metadata = detail.get("metadata") or {}
        storyboard = detail.get("storyboard")
        storyboard_dict = None
        if storyboard is not None and pixelle_video.persistence is not None:
            storyboard_dict = pixelle_video.persistence._storyboard_to_dict(storyboard)
            if storyboard_dict.get("final_video_path"):
                storyboard_dict["final_video_url"] = path_to_url(
                    request,
                    storyboard_dict["final_video_path"],
                )

        result = dict(metadata.get("result") or {})
        if result.get("video_path"):
            result["video_url"] = path_to_url(request, result["video_path"])

        return {
            "success": True,
            "metadata": metadata,
            "result": result,
            "storyboard": storyboard_dict,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{task_id}")
async def delete_history_task(task_id: str, pixelle_video: PixelleVideoDep):
    """Delete a persisted task and generated files."""
    try:
        deleted = await pixelle_video.history.delete_task(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
        return {"success": True, "message": "Task deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{task_id}/resume")
async def resume_history_task(task_id: str, pixelle_video: PixelleVideoDep):
    """Resume a failed or interrupted standard generation task synchronously."""
    try:
        def progress_callback(event: ProgressEvent):
            logger.info(
                f"Resume {task_id}: {event.event_type} {int(event.progress * 100)}%"
            )

        result = await pixelle_video.history.resume_task(
            task_id,
            pixelle_video,
            progress_callback=progress_callback,
        )
        return {
            "success": True,
            "video_path": result.video_path,
            "duration": result.duration,
        }
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

