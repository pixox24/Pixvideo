"""Safe, server-owned uploads for specialist video workflows."""

from __future__ import annotations

import shutil
import json
from pathlib import Path
from pathlib import PurePosixPath
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from api.schemas.uploads import UploadPurpose, UploadResponse, UploadedFile
from pixelle_video.utils.os_util import get_data_path

router = APIRouter(prefix="/uploads", tags=["Uploads"])

MAX_FILE_SIZE_BYTES = 512 * 1024 * 1024
MAX_BATCH_SIZE_BYTES = 1024 * 1024 * 1024
MAX_FILES_PER_REQUEST = 20
CHUNK_SIZE_BYTES = 1024 * 1024

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
PURPOSE_EXTENSIONS = {
    UploadPurpose.CUSTOM_MEDIA: IMAGE_EXTENSIONS | VIDEO_EXTENSIONS,
    UploadPurpose.IMAGE_TO_VIDEO: IMAGE_EXTENSIONS - {".gif"},
    UploadPurpose.ACTION_TRANSFER_VIDEO: {".mp4", ".mkv", ".mov"},
    UploadPurpose.ACTION_TRANSFER_IMAGE: IMAGE_EXTENSIONS - {".gif"},
    UploadPurpose.DIGITAL_HUMAN_CHARACTER: IMAGE_EXTENSIONS - {".gif"},
    UploadPurpose.DIGITAL_HUMAN_PRODUCT: IMAGE_EXTENSIONS - {".gif"},
}


def _validate_uploads(purpose: UploadPurpose, files: list[UploadFile]) -> None:
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=413,
            detail=f"A maximum of {MAX_FILES_PER_REQUEST} files may be uploaded at once",
        )

    allowed_extensions = PURPOSE_EXTENSIONS[purpose]
    for upload in files:
        filename = upload.filename or ""
        extension = Path(filename).suffix.lower()
        if not filename or extension not in allowed_extensions:
            allowed = ", ".join(sorted(ext.removeprefix(".") for ext in allowed_extensions))
            raise HTTPException(
                status_code=415,
                detail=f"{filename or 'Unnamed file'} is not supported for {purpose.value}. Allowed: {allowed}",
            )


def resolve_uploaded_file_keys(file_keys: list[str], purpose: UploadPurpose) -> list[str]:
    """Resolve server-issued upload keys and verify their owning workflow."""
    if not file_keys:
        raise HTTPException(status_code=422, detail="At least one uploaded file is required")

    uploads_root = Path(get_data_path("uploads")).resolve()
    manifests: dict[str, dict] = {}
    resolved_paths: list[str] = []

    for file_key in file_keys:
        key_path = PurePosixPath(file_key)
        if key_path.is_absolute() or len(key_path.parts) != 4 or key_path.parts[:2] != ("data", "uploads"):
            raise HTTPException(status_code=422, detail="Invalid uploaded file key")

        upload_id, stored_name = key_path.parts[2:]
        file_path = (uploads_root / upload_id / stored_name).resolve()
        try:
            file_path.relative_to(uploads_root)
        except ValueError as error:
            raise HTTPException(status_code=422, detail="Invalid uploaded file key") from error

        if upload_id not in manifests:
            manifest_path = uploads_root / upload_id / "manifest.json"
            try:
                manifests[upload_id] = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                raise HTTPException(status_code=422, detail="Uploaded file batch was not found") from error

        manifest = manifests[upload_id]
        valid_keys = {item.get("file_key") for item in manifest.get("files", [])}
        if manifest.get("purpose") != purpose.value or file_key not in valid_keys or not file_path.is_file():
            raise HTTPException(status_code=422, detail="Uploaded file is not valid for this workflow")

        resolved_paths.append(str(file_path))

    return resolved_paths


@router.post("", response_model=UploadResponse)
async def upload_files(
    purpose: Annotated[UploadPurpose, Query(description="Specialist workflow that will consume the files")],
    files: Annotated[list[UploadFile], File(description="One or more media files")],
) -> UploadResponse:
    """Store a validated batch of specialist media and return safe file keys.

    The request is atomic from the caller's perspective: any validation or write
    failure removes the batch directory, so callers never receive partial keys.
    """
    _validate_uploads(purpose, files)

    upload_id = uuid4().hex
    upload_dir = Path(get_data_path("uploads", upload_id)).resolve()
    stored_files: list[UploadedFile] = []
    batch_size = 0

    try:
        upload_dir.mkdir(parents=True, exist_ok=False)
        for index, upload in enumerate(files, start=1):
            extension = Path(upload.filename or "").suffix.lower()
            stored_name = f"file-{index:02d}{extension}"
            destination = upload_dir / stored_name
            temporary_destination = destination.with_suffix(f"{extension}.part")
            file_size = 0

            with temporary_destination.open("wb") as target:
                while chunk := await upload.read(CHUNK_SIZE_BYTES):
                    file_size += len(chunk)
                    batch_size += len(chunk)
                    if file_size > MAX_FILE_SIZE_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"{upload.filename} exceeds the {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB limit",
                        )
                    if batch_size > MAX_BATCH_SIZE_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Upload batch exceeds the {MAX_BATCH_SIZE_BYTES // (1024 * 1024)} MB limit",
                        )
                    target.write(chunk)

            temporary_destination.replace(destination)
            file_key = f"data/uploads/{upload_id}/{stored_name}"
            stored_files.append(
                UploadedFile(
                    file_key=file_key,
                    filename=upload.filename or stored_name,
                    content_type=upload.content_type or "application/octet-stream",
                    size=file_size,
                    url=f"/api/files/{file_key}",
                )
            )

        manifest_payload = {
            "purpose": purpose.value,
            "files": [{"file_key": item.file_key} for item in stored_files],
        }
        manifest_path = upload_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
    except HTTPException:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise
    except OSError as error:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail="Unable to store uploaded files") from error
    finally:
        for upload in files:
            await upload.close()

    return UploadResponse(upload_id=upload_id, purpose=purpose, files=stored_files)
