"""Reference-image style analysis and reusable style-slot APIs."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from pixelle_video.config import config_manager
from pixelle_video.services.style_slot_repository import StyleSlotRepository
from pixelle_video.services.vision_understanding import analyze_style_image, prepare_image_data_url

router = APIRouter(prefix="/style-slots", tags=["Style Slots"])
repository = StyleSlotRepository()
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


async def _read_reference_image(file: UploadFile) -> bytes:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail={"code": "vision_image_invalid", "message": "仅支持 JPG、PNG 或 WebP 参考图"})
    data = await file.read()
    max_bytes = int(config_manager.get_vision_understanding_config().get("max_image_bytes", 10 * 1024 * 1024))
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail={"code": "vision_image_too_large", "message": "参考图超过大小限制"})
    return data


class StyleSlotCreate(BaseModel):
    name: str = Field(default="", max_length=80)
    style_prefix: str = Field(min_length=1, max_length=1200)
    style_tags: list[str] = Field(default_factory=list)
    visual_features: dict = Field(default_factory=dict)
    negative_constraints: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    strength: int = Field(default=70, ge=0, le=100)
    image_data: str | None = None


def _error(exc: Exception) -> HTTPException:
    code = str(exc) or "vision_model_failed"
    status = 422 if code in {"vision_understanding_not_configured", "vision_image_invalid", "vision_image_too_large", "style_prefix_empty", "vision_response_invalid"} else 502
    return HTTPException(status_code=status, detail={"code": code, "message": code})


@router.get("")
async def list_style_slots():
    return {"success": True, "slots": repository.list()}


@router.post("/analyze")
async def analyze_style(file: UploadFile = File(...)):
    try:
        data = await _read_reference_image(file)
        style = await analyze_style_image(data, file.content_type)
        return {"success": True, "style": style}
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await file.close()


@router.post("")
async def create_style_slot(
    file: UploadFile = File(...),
    style_json: str = Form(...),
): 
    import json
    try:
        payload = StyleSlotCreate.model_validate(json.loads(style_json))
    except Exception as exc:
        raise _error(ValueError("style_prefix_empty")) from exc
    if not payload.style_prefix.strip():
        raise _error(ValueError("style_prefix_empty"))
    try:
        image_bytes = await _read_reference_image(file)
        style = payload.model_dump(exclude={"name", "image_data", "strength"})
        return {"success": True, "slot": repository.create(name=payload.name, image_bytes=image_bytes, style=style, strength=payload.strength)}
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(exc) from exc
    finally:
        await file.close()


@router.patch("/{slot_id}")
async def update_style_slot(slot_id: str, payload: dict):
    try:
        updated = repository.update(slot_id, payload)
    except Exception as exc:
        raise _error(exc) from exc
    if not updated:
        raise HTTPException(status_code=404, detail="style slot not found")
    return {"success": True, "slot": updated}


@router.delete("/{slot_id}")
async def delete_style_slot(slot_id: str):
    if not repository.delete(slot_id):
        raise HTTPException(status_code=404, detail="style slot not found")
    return {"success": True}


@router.get("/{slot_id}/image")
async def style_slot_image(slot_id: str):
    slot = repository.get(slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="style slot not found")
    path = Path(repository.media_root) / slot_id / "reference.jpg"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="style reference not found")
    return FileResponse(path, media_type="image/jpeg")
