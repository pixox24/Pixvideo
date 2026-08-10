"""Request schemas for specialist generation workflows."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from api.schemas.video import VideoGenerateAsyncResponse


class CustomMediaGenerateRequest(BaseModel):
    """Generate a video using uploaded image and video assets."""

    asset_file_keys: list[str] = Field(min_length=1, max_length=20)
    title: str = Field(default="", max_length=200)
    intent: str | None = Field(default=None, max_length=4000)
    duration: int = Field(default=30, ge=5, le=300)
    source: Literal["runninghub", "selfhost"] = "runninghub"
    bgm_path: str | None = None
    bgm_volume: float = Field(default=0.2, ge=0.0, le=1.0)
    bgm_mode: Literal["loop", "once"] = "loop"
    voice_id: str | None = None
    tts_speed: float = Field(default=1.2, ge=0.5, le=2.0)


class ImageToVideoGenerateRequest(BaseModel):
    """Generate video motion from one uploaded image and an I2V workflow."""

    image_file_key: str
    prompt: str = Field(min_length=1, max_length=4000)
    workflow_key: str = Field(min_length=1, max_length=300)
    title: str = Field(default="", max_length=200)


class ActionTransferGenerateRequest(BaseModel):
    """Transfer the motion of an uploaded video onto an uploaded subject image."""

    video_file_key: str
    image_file_key: str
    prompt: str = Field(min_length=1, max_length=4000)
    workflow_key: str = Field(default="runninghub/af_scail.json", min_length=1, max_length=300)
    duration: int = Field(default=15, ge=1, le=30)
    title: str = Field(default="", max_length=200)


class DigitalHumanGenerateRequest(BaseModel):
    """Generate a digital-human video in direct-script or product mode."""

    mode: Literal["customize", "digital"]
    character_file_key: str
    product_file_key: str | None = None
    product_title: str | None = Field(default=None, max_length=300)
    script: str = Field(default="", max_length=8000)
    tts_inference_mode: Literal["local", "minimax", "comfyui", "mimo"] = "local"
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    title: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def validate_mode_inputs(self):
        if self.mode == "customize" and not self.script.strip():
            raise ValueError("script is required for customize mode")
        if self.mode == "digital" and not self.product_file_key:
            raise ValueError("product_file_key is required for digital mode")
        if self.mode == "digital" and not (self.script.strip() or (self.product_title or "").strip()):
            raise ValueError("script or product_title is required for digital mode")
        return self


__all__ = ["CustomMediaGenerateRequest", "ImageToVideoGenerateRequest", "ActionTransferGenerateRequest", "DigitalHumanGenerateRequest", "VideoGenerateAsyncResponse"]
