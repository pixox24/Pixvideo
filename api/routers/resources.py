# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Resource discovery endpoints

Provides endpoints to discover available workflows, templates, and BGM.
"""

import platform
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.schemas.resources import (
    BGMInfo,
    BGMListResponse,
    FontInfo,
    FontListResponse,
    TemplateInfo,
    TemplateListResponse,
    WorkflowInfo,
    WorkflowListResponse,
)
from pixelle_video.config import config_manager
from pixelle_video.utils.os_util import get_data_path, get_root_path
from pixelle_video.utils.template_util import get_all_templates_with_info

router = APIRouter(prefix="/resources", tags=["Resources"])

FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
SYSTEM_FONT_DIRS = (
    Path("/System/Library/Fonts"),
    Path("/Library/Fonts"),
    Path.home() / "Library/Fonts",
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
    Path("C:/Windows/Fonts"),
)


def _font_name(path: Path) -> str:
    """Return a readable font name from a font file path."""
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


def _collect_fonts_from_dir(base: Path, source: str) -> list[FontInfo]:
    """Collect subtitle font files from a folder recursively."""
    if not base.exists() or not base.is_dir():
        return []

    fonts: list[FontInfo] = []
    for item in sorted(base.rglob("*")):
        if item.is_file() and item.suffix.lower() in FONT_EXTENSIONS:
            fonts.append(
                FontInfo(
                    name=_font_name(item),
                    path=str(item),
                    source=source,
                )
            )
    return fonts


def _font_candidates() -> list[tuple[Path, str]]:
    """Return every directory approved for subtitle font discovery."""
    candidates: list[tuple[Path, str]] = [
        (Path(get_root_path("resources", "fonts")), "project"),
        (Path(get_data_path("fonts")), "data"),
        *[(path, "system") for path in SYSTEM_FONT_DIRS],
    ]
    custom_font_folder = str(config_manager.get("subtitle", {}).get("custom_font_folder") or "").strip()
    if custom_font_folder:
        candidates.append((Path(custom_font_folder).expanduser().resolve(), "custom-folder"))
    return candidates


def _approved_font_path(value: str) -> Path | None:
    """Resolve a requested font only when it is inside a discovered font directory."""
    try:
        font_path = Path(value).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    if not font_path.is_file() or font_path.suffix.lower() not in FONT_EXTENSIONS:
        return None

    for base, _source in _font_candidates():
        try:
            font_path.relative_to(base.expanduser().resolve())
            return font_path
        except (OSError, RuntimeError, ValueError):
            continue
    return None


@router.get("/workflows/tts", response_model=WorkflowListResponse)
async def list_tts_workflows(pixelle_video: PixelleVideoDep):
    """
    List available TTS workflows
    
    Returns list of TTS workflows from both RunningHub and self-hosted sources.
    
    Example response:
    ```json
    {
        "workflows": [
            {
                "name": "tts_edge.json",
                "display_name": "tts_edge.json - Runninghub",
                "source": "runninghub",
                "path": "workflows/runninghub/tts_edge.json",
                "key": "runninghub/tts_edge.json",
                "workflow_id": "123456"
            }
        ]
    }
    ```
    """
    try:
        # Get all workflows from TTS service
        all_workflows = pixelle_video.tts.list_workflows()
        
        # Filter to TTS workflows only (filename starts with "tts_")
        tts_workflows = [
            WorkflowInfo(**wf) 
            for wf in all_workflows 
            if wf["name"].startswith("tts_")
        ]
        
        return WorkflowListResponse(workflows=tts_workflows)
        
    except Exception as e:
        logger.error(f"List TTS workflows error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/media", response_model=WorkflowListResponse)
async def list_media_workflows(pixelle_video: PixelleVideoDep):
    """
    List available media workflows (both image and video)
    
    Returns list of all media workflows from both RunningHub and self-hosted sources.
    
    Example response:
    ```json
    {
        "workflows": [
            {
                "name": "image_flux.json",
                "display_name": "image_flux.json - Runninghub",
                "source": "runninghub",
                "path": "workflows/runninghub/image_flux.json",
                "key": "runninghub/image_flux.json",
                "workflow_id": "123456"
            },
            {
                "name": "video_wan2.1.json",
                "display_name": "video_wan2.1.json - Runninghub",
                "source": "runninghub",
                "path": "workflows/runninghub/video_wan2.1.json",
                "key": "runninghub/video_wan2.1.json",
                "workflow_id": "123457"
            }
        ]
    }
    ```
    """
    try:
        # Get all workflows from media service (includes both image and video)
        all_workflows = pixelle_video.media.list_workflows()
        
        media_workflows = [WorkflowInfo(**wf) for wf in all_workflows]
        
        return WorkflowListResponse(workflows=media_workflows)
        
    except Exception as e:
        logger.error(f"List media workflows error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Keep old endpoint for backward compatibility
@router.get("/workflows/image", response_model=WorkflowListResponse)
async def list_image_workflows(pixelle_video: PixelleVideoDep):
    """
    List available image workflows (deprecated, use /workflows/media instead)
    
    This endpoint is kept for backward compatibility but will filter to image_ workflows only.
    """
    try:
        all_workflows = pixelle_video.media.list_workflows()
        
        # Filter to image workflows only (filename starts with "image_")
        image_workflows = [
            WorkflowInfo(**wf) 
            for wf in all_workflows 
            if wf["name"].startswith("image_")
        ]
        
        return WorkflowListResponse(workflows=image_workflows)
        
    except Exception as e:
        logger.error(f"List image workflows error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates():
    """
    List available video templates
    
    Returns list of HTML templates grouped by size (portrait, landscape, square).
    Templates are merged from both default (templates/) and custom (data/templates/) directories.
    
    Example response:
    ```json
    {
        "templates": [
            {
                "name": "default.html",
                "display_name": "default.html",
                "size": "1080x1920",
                "width": 1080,
                "height": 1920,
                "orientation": "portrait",
                "path": "templates/1080x1920/default.html",
                "key": "1080x1920/default.html"
            }
        ]
    }
    ```
    """
    try:
        # Get all templates with info
        all_templates = get_all_templates_with_info()
        
        # Convert to API response format
        templates = []
        for t in all_templates:
            templates.append(TemplateInfo(
                name=t.display_info.name,
                display_name=t.display_info.name,
                size=t.display_info.size,
                width=t.display_info.width,
                height=t.display_info.height,
                orientation=t.display_info.orientation,
                path=t.template_path,
                key=t.template_path
            ))
        
        return TemplateListResponse(templates=templates)
        
    except Exception as e:
        logger.error(f"List templates error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bgm", response_model=BGMListResponse)
async def list_bgm():
    """
    List available background music files
    
    Returns list of BGM files merged from both default (bgm/) and custom (data/bgm/) directories.
    Custom files take precedence over default files with the same name.
    
    Supported formats: mp3, wav, flac, m4a, aac, ogg
    
    Example response:
    ```json
    {
        "bgm_files": [
            {
                "name": "default.mp3",
                "path": "bgm/default.mp3",
                "source": "default"
            },
            {
                "name": "happy.mp3",
                "path": "data/bgm/happy.mp3",
                "source": "custom"
            }
        ]
    }
    ```
    """
    try:
        # Supported audio extensions
        audio_extensions = ('.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg')
        
        # Collect BGM files from both locations
        bgm_files_dict = {}  # {filename: {"path": str, "source": str}}
        
        # Scan default bgm/ directory
        default_bgm_dir = Path(get_root_path("bgm"))
        if default_bgm_dir.exists() and default_bgm_dir.is_dir():
            for item in default_bgm_dir.iterdir():
                if item.is_file() and item.suffix.lower() in audio_extensions:
                    bgm_files_dict[item.name] = {
                        "path": f"bgm/{item.name}",
                        "source": "default"
                    }
        
        # Scan custom data/bgm/ directory (overrides default)
        custom_bgm_dir = Path(get_data_path("bgm"))
        if custom_bgm_dir.exists() and custom_bgm_dir.is_dir():
            for item in custom_bgm_dir.iterdir():
                if item.is_file() and item.suffix.lower() in audio_extensions:
                    bgm_files_dict[item.name] = {
                        "path": f"data/bgm/{item.name}",
                        "source": "custom"
                    }

        selected_bgm_folder = str(config_manager.get("quick_create", {}).get("custom_bgm_folder") or "").strip()
        selected_bgm_dir = Path(selected_bgm_folder) if selected_bgm_folder else None
        if selected_bgm_dir and selected_bgm_dir.exists() and selected_bgm_dir.is_dir():
            for item in selected_bgm_dir.iterdir():
                if item.is_file() and item.suffix.lower() in audio_extensions:
                    bgm_files_dict[item.name] = {
                        "path": f"custom-bgm/{item.name}",
                        "source": "custom-folder",
                    }
        
        # Convert to response format
        bgm_files = [
            BGMInfo(
                name=name,
                path=info["path"],
                source=info["source"]
            )
            for name, info in sorted(bgm_files_dict.items())
        ]
        
        return BGMListResponse(bgm_files=bgm_files)
        
    except Exception as e:
        logger.error(f"List BGM error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fonts", response_model=FontListResponse)
async def list_fonts():
    """
    List available subtitle font files.

    Fonts are discovered from project resources, data/fonts, system font folders,
    and the user-selected custom font folder.
    """
    try:
        font_map: dict[str, FontInfo] = {}
        for base, source in _font_candidates():
            for font in _collect_fonts_from_dir(base, source):
                font_map[font.path] = font

        fonts = sorted(
            font_map.values(),
            key=lambda item: (
                0 if item.source == "custom-folder" else 1 if item.source in {"project", "data"} else 2,
                item.name.lower(),
            ),
        )
        return FontListResponse(fonts=fonts)
    except Exception as e:
        logger.error(f"List fonts error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fonts/file")
async def get_font_file(path: str):
    """Serve a selected, discovered font for browser-side subtitle previews."""
    font_path = _approved_font_path(path)
    if not font_path:
        raise HTTPException(status_code=404, detail="字体文件不存在或不在已选择的字体目录中。")

    media_types = {
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".ttc": "font/collection",
    }
    return FileResponse(font_path, media_type=media_types.get(font_path.suffix.lower()))


@router.post("/fonts/select-folder")
async def select_custom_font_folder():
    """Select and persist a custom subtitle font folder."""
    try:
        system_name = platform.system()
        if system_name != "Darwin":
            raise HTTPException(status_code=501, detail="当前仅支持 macOS 文件夹选择。")

        script = 'POSIX path of (choose folder with prompt "选择自定义字幕字体文件夹")'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )
        selected_path = result.stdout.strip()
        if not selected_path:
            raise HTTPException(status_code=400, detail="未选择字体文件夹。")

        selected_folder = Path(selected_path).expanduser().resolve()
        if not selected_folder.exists() or not selected_folder.is_dir():
            raise HTTPException(status_code=400, detail="选择的路径不是有效文件夹。")

        config_manager.update({"subtitle": {"custom_font_folder": str(selected_folder)}})
        config_manager.save()
        return {"success": True, "path": str(selected_folder)}
    except HTTPException:
        raise
    except subprocess.CalledProcessError as exc:
        logger.info(f"Custom font folder selection cancelled or failed: {exc}")
        raise HTTPException(status_code=400, detail="已取消选择自定义字幕字体文件夹。") from exc
    except Exception as e:
        logger.error(f"Select custom font folder error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bgm/open-folder")
async def open_custom_bgm_folder():
    """Open the custom BGM folder used by resource discovery."""
    try:
        custom_bgm_dir = Path(get_data_path("bgm"))
        custom_bgm_dir.mkdir(parents=True, exist_ok=True)

        system_name = platform.system()
        if system_name == "Darwin":
            command = ["open", str(custom_bgm_dir)]
        elif system_name == "Windows":
            command = ["explorer", str(custom_bgm_dir)]
        else:
            command = ["xdg-open", str(custom_bgm_dir)]

        subprocess.Popen(command)
        return {"success": True, "path": str(custom_bgm_dir)}
    except Exception as e:
        logger.error(f"Open custom BGM folder error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bgm/select-folder")
async def select_custom_bgm_folder():
    """Select and persist a custom BGM folder."""
    try:
        system_name = platform.system()
        if system_name != "Darwin":
            raise HTTPException(status_code=501, detail="当前仅支持 macOS 文件夹选择。")

        script = 'POSIX path of (choose folder with prompt "选择自定义音乐文件夹")'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )
        selected_path = result.stdout.strip()
        if not selected_path:
            raise HTTPException(status_code=400, detail="未选择文件夹。")

        selected_folder = Path(selected_path).expanduser().resolve()
        if not selected_folder.exists() or not selected_folder.is_dir():
            raise HTTPException(status_code=400, detail="选择的路径不是有效文件夹。")

        config_manager.update({"quick_create": {"custom_bgm_folder": str(selected_folder)}})
        config_manager.save()
        return {"success": True, "path": str(selected_folder)}
    except HTTPException:
        raise
    except subprocess.CalledProcessError as exc:
        logger.info(f"Custom BGM folder selection cancelled or failed: {exc}")
        raise HTTPException(status_code=400, detail="已取消选择自定义音乐文件夹。") from exc
    except Exception as e:
        logger.error(f"Select custom BGM folder error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
