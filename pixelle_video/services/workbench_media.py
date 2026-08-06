"""Project-local media storage for the editing workbench."""

from __future__ import annotations

import base64
import shutil
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from PIL import Image


class WorkbenchMediaStore:
    def __init__(self, root: str | Path = "data/workbench/projects", *, max_bytes: int = 50 * 1024 * 1024):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes

    def project_root(self, project_id: str) -> Path:
        if not project_id or Path(project_id).name != project_id:
            raise ValueError("invalid project id")
        return self.root / project_id

    def resolve(self, project_id: str, relative_path: str) -> Path:
        project_root = self.project_root(project_id).resolve()
        candidate = (project_root / relative_path).resolve()
        try:
            candidate.relative_to(project_root)
        except ValueError as exc:
            raise ValueError("path is outside project root") from exc
        return candidate

    def copy_upload(self, project_id: str, scene_id: str, source: Path, filename: str) -> str:
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(source)
        safe_name = Path(filename).name
        if not safe_name or safe_name in {".", ".."}:
            raise ValueError("invalid filename")
        destination_relative = f"assets/scenes/{scene_id}/uploads/{safe_name}"
        destination = self.resolve(project_id, destination_relative)
        self._validate_image(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination_relative

    async def download_result(self, project_id: str, scene_id: str, source_url: str, version_id: str) -> str:
        parsed = urlparse(source_url)
        suffix = Path(parsed.path).suffix.lower() or ".png"
        relative = f"assets/scenes/{scene_id}/generated/{version_id}{suffix}"
        destination = self.resolve(project_id, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".tmp")
        try:
            if parsed.scheme in {"http", "https"}:
                timeout = httpx.Timeout(connect=10, read=60, write=60, pool=60)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream("GET", source_url) as response:
                        response.raise_for_status()
                        content_length = response.headers.get("content-length")
                        if content_length and int(content_length) > self.max_bytes:
                            raise ValueError("download exceeds size limit")
                        size = 0
                        with temporary.open("wb") as handle:
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > self.max_bytes:
                                    raise ValueError("download exceeds size limit")
                                handle.write(chunk)
            elif parsed.scheme == "" and Path(source_url).is_file():
                source = Path(source_url).resolve()
                if source.stat().st_size > self.max_bytes:
                    raise ValueError("source exceeds size limit")
                shutil.copyfile(source, temporary)
            else:
                raise ValueError("source URL must be http(s) or an existing local file")
            self._validate_image(temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        return relative

    @staticmethod
    async def download_to_path(source_url: str, output_path: str | Path) -> str:
        """Download or copy a media URL to an explicit destination."""
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_path = Path(source_url)
        if source_path.exists():
            if source_path.resolve() != destination.resolve():
                shutil.copyfile(source_path, destination)
            return str(destination)
        if source_url.startswith("data:"):
            payload = source_url.split(",", 1)[1] if "," in source_url else source_url
            destination.write_bytes(base64.b64decode(payload))
            return str(destination)
        timeout = httpx.Timeout(connect=10.0, read=60, write=60, pool=60)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(source_url)
            response.raise_for_status()
            destination.write_bytes(response.content)
        return str(destination)

    def create_thumbnail(self, absolute_path: Path, relative_path: str) -> str:
        source = Path(absolute_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        image = self._validate_image(source)
        thumbnail_relative = f"assets/thumbnails/{Path(relative_path).stem}.jpg"
        destination = self.resolve(self._project_id_for(source), thumbnail_relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.thumbnail((320, 320), Image.Resampling.LANCZOS)
        if image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        image.save(destination, format="JPEG", quality=85)
        return thumbnail_relative

    def _project_id_for(self, path: Path) -> str:
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("path is outside project root") from exc
        if not relative.parts:
            raise ValueError("path is not inside a project")
        return relative.parts[0]

    def to_api_url(self, project_id: str, relative_path: str, request=None) -> str:
        del request
        self.resolve(project_id, relative_path)
        return f"/api/workbench/projects/{quote(project_id)}/media/{quote(relative_path, safe='/')}"

    @staticmethod
    def _validate_image(path: Path) -> Image.Image:
        try:
            with Image.open(path) as image:
                image.verify()
            image = Image.open(path)
            image.load()
            return image
        except Exception as exc:
            raise ValueError("file is not a valid image") from exc
