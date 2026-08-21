from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from api.routers import files, uploads
from api.schemas.uploads import UploadPurpose


def make_upload(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.asyncio
async def test_uploads_store_safe_file_keys_and_preview_urls(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "get_data_path", lambda *parts: str(tmp_path.joinpath("data", *parts)))

    response = await uploads.upload_files(
        UploadPurpose.IMAGE_TO_VIDEO,
        [make_upload("camping.png", b"image-data", "image/png")],
    )

    stored = response.files[0]
    assert response.purpose is UploadPurpose.IMAGE_TO_VIDEO
    assert stored.filename == "camping.png"
    assert stored.size == len(b"image-data")
    assert stored.file_key == f"data/uploads/{response.upload_id}/file-01.png"
    assert stored.url == f"/api/files/{stored.file_key}"
    assert (tmp_path / stored.file_key).read_bytes() == b"image-data"


@pytest.mark.asyncio
async def test_uploads_reject_files_not_allowed_for_purpose(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "get_data_path", lambda *parts: str(tmp_path.joinpath("data", *parts)))

    with pytest.raises(HTTPException, match="not supported") as error:
        await uploads.upload_files(
            UploadPurpose.IMAGE_TO_VIDEO,
            [make_upload("source.mp4", b"video-data", "video/mp4")],
        )

    assert error.value.status_code == 415
    assert not (tmp_path / "uploads").exists()


@pytest.mark.asyncio
async def test_uploads_clean_up_an_oversized_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "get_data_path", lambda *parts: str(tmp_path.joinpath("data", *parts)))
    monkeypatch.setattr(uploads, "MAX_FILE_SIZE_BYTES", 3)

    with pytest.raises(HTTPException, match="exceeds") as error:
        await uploads.upload_files(
            UploadPurpose.IMAGE_TO_VIDEO,
            [make_upload("source.png", b"1234", "image/png")],
        )

    assert error.value.status_code == 413
    uploads_root = tmp_path / "data" / "uploads"
    assert uploads_root.exists()
    assert list(uploads_root.iterdir()) == []


@pytest.mark.asyncio
async def test_file_router_serves_uploaded_media_from_data_directory(tmp_path, monkeypatch):
    upload = tmp_path / "data" / "uploads" / "batch" / "file-01.webp"
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b"webp")
    monkeypatch.chdir(tmp_path)

    response = await files.get_file("data/uploads/batch/file-01.webp")

    assert response.path == str(upload)
    assert response.media_type == "image/webp"


def test_uploaded_file_keys_require_a_matching_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "get_data_path", lambda *parts: str(tmp_path.joinpath("data", *parts)))
    upload_dir = tmp_path / "data" / "uploads" / "batch"
    upload_dir.mkdir(parents=True)
    file_key = "data/uploads/batch/file-01.png"
    (upload_dir / "file-01.png").write_bytes(b"image")
    (upload_dir / "manifest.json").write_text(
        '{"purpose":"image-to-video","files":[{"file_key":"data/uploads/batch/other.png"}]}',
        encoding="utf-8",
    )

    with pytest.raises(HTTPException, match="not valid"):
        uploads.resolve_uploaded_file_keys([file_key], UploadPurpose.IMAGE_TO_VIDEO)
