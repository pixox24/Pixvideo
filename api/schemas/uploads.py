"""Schemas for user-uploaded specialist media."""

from enum import Enum

from pydantic import BaseModel, Field


class UploadPurpose(str, Enum):
    """The specialist workflow that owns an uploaded file."""

    IMAGE_TO_VIDEO = "image-to-video"


class UploadedFile(BaseModel):
    """A server-owned uploaded file safe to reference in later API calls."""

    file_key: str = Field(description="Stable project-relative key for the uploaded file")
    filename: str = Field(description="Original filename for display")
    content_type: str = Field(description="Client-declared or inferred MIME type")
    size: int = Field(ge=0, description="File size in bytes")
    url: str = Field(description="API URL for browser preview")


class UploadResponse(BaseModel):
    """Response returned after an atomic upload batch succeeds."""

    upload_id: str
    purpose: UploadPurpose
    files: list[UploadedFile]
