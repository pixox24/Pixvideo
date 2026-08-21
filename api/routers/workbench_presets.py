"""Quick Create preset and prompt-prefix endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.routers.workbench_support import (
    PromptPrefixSaveRequest,
    _find_preset_or_404,
    _legacy_preset_from_config,
    _normalize_preset,
    _preset_response,
    _quick_create_config_from_preset,
    _read_presets_store,
    _write_presets_store,
)
from pixelle_video.config import config_manager

router = APIRouter()


@router.get("/presets")
async def list_presets():
    """Return all saved quick-create presets and the current default preset."""
    store = _read_presets_store()
    return _preset_response(store)


@router.post("/presets")
async def save_preset(preset: dict[str, Any]):
    """Create a new reusable quick-create preset from the current React state."""
    try:
        store = _read_presets_store()
        existing_presets = [
            item for item in store["presets"] if item.get("id") != "quick-create-default"
        ]
        saved = _normalize_preset(preset)
        presets = [*existing_presets, saved]
        store = {"defaultPresetId": saved["id"], "presets": presets}
        _write_presets_store(store)
        config_manager.save_quick_create_config(_quick_create_config_from_preset(saved))
        return _preset_response(store, saved)
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/presets/{preset_id}")
async def update_preset(preset_id: str, preset: dict[str, Any]):
    """Overwrite an existing reusable quick-create preset."""
    try:
        store = _read_presets_store()
        existing = _find_preset_or_404(store, preset_id)
        saved = _normalize_preset({**preset, "id": preset_id}, existing=existing)
        store["presets"] = [
            saved if item["id"] == preset_id else item for item in store["presets"]
        ]
        if not store.get("defaultPresetId"):
            store["defaultPresetId"] = preset_id
        _write_presets_store(store)
        config_manager.save_quick_create_config(_quick_create_config_from_preset(saved))
        return _preset_response(store, saved)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/presets/{preset_id}/default")
async def set_default_preset(preset_id: str):
    """Set an existing preset as the default quick-create preset."""
    try:
        store = _read_presets_store()
        preset = _find_preset_or_404(store, preset_id)
        store["defaultPresetId"] = preset_id
        _write_presets_store(store)
        config_manager.save_quick_create_config(_quick_create_config_from_preset(preset))
        return _preset_response(store, preset)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str):
    """Delete a reusable quick-create preset."""
    try:
        store = _read_presets_store()
        _find_preset_or_404(store, preset_id)
        remaining = [item for item in store["presets"] if item["id"] != preset_id]
        if not remaining:
            fallback = _legacy_preset_from_config()
            remaining = [fallback]
            default_preset_id = fallback["id"]
        elif store.get("defaultPresetId") == preset_id:
            default_preset_id = remaining[0]["id"]
        else:
            default_preset_id = store.get("defaultPresetId") or remaining[0]["id"]

        store = {"defaultPresetId": default_preset_id, "presets": remaining}
        active_preset = next(
            (item for item in remaining if item["id"] == default_preset_id),
            remaining[0],
        )
        _write_presets_store(store)
        config_manager.save_quick_create_config(_quick_create_config_from_preset(active_preset))
        return _preset_response(store, active_preset)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/prompt-prefix")
async def save_prompt_prefix(request: PromptPrefixSaveRequest):
    """Persist only the shared prompt prefix without touching other quick-create settings."""
    try:
        config_manager.set_prompt_prefix(request.promptPrefix)
        store = _read_presets_store()
        preset_id = request.presetId or store["defaultPresetId"]
        existing = _find_preset_or_404(store, preset_id)
        saved = _normalize_preset(
            {"id": preset_id, "promptPrefix": request.promptPrefix},
            existing=existing,
        )
        store["presets"] = [
            saved if item["id"] == preset_id else item for item in store["presets"]
        ]
        _write_presets_store(store)
        config_manager.save_quick_create_config(_quick_create_config_from_preset(saved))
        return {
            **_preset_response(store, saved),
            "promptPrefix": saved.get("promptPrefix", ""),
        }
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
