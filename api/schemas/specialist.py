"""Request schemas for image-to-video generation."""

from pydantic import BaseModel, Field

from api.schemas.video import VideoGenerateAsyncResponse


class ImageToVideoGenerateRequest(BaseModel):
    """Generate video motion from one uploaded image and an I2V workflow."""

    image_file_key: str
    prompt: str = Field(min_length=1, max_length=4000)
    workflow_key: str = Field(min_length=1, max_length=300)
    title: str = Field(default="", max_length=200)


__all__ = ["ImageToVideoGenerateRequest", "VideoGenerateAsyncResponse"]
