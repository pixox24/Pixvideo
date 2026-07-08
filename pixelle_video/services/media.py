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
Media Generation Service - ComfyUI Workflow-based implementation

Supports both image and video generation workflows.
Automatically detects output type based on ExecuteResult.
"""

import asyncio
import base64
import os
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx
from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.models.media import MediaResult
from pixelle_video.services.comfy_base_service import ComfyBaseService


class MediaService(ComfyBaseService):
    """
    Media generation service - Workflow-based
    
    Uses ComfyKit to execute image/video generation workflows.
    Supports both image_ and video_ workflow prefixes.
    
    Usage:
        # Use default workflow (workflows/image_flux.json)
        media = await pixelle_video.media(prompt="a cat")
        if media.is_image:
            print(f"Generated image: {media.url}")
        elif media.is_video:
            print(f"Generated video: {media.url} ({media.duration}s)")
        
        # Use specific workflow
        media = await pixelle_video.media(
            prompt="a cat",
            workflow="image_flux.json"
        )
        
        # List available workflows
        workflows = pixelle_video.media.list_workflows()
    """
    
    WORKFLOW_PREFIX = ""  # Will be overridden by _scan_workflows
    DEFAULT_WORKFLOW = None  # No hardcoded default, must be configured
    WORKFLOWS_DIR = "workflows"
    BIZYAIR_API_BASE = "https://api.bizyair.cn/x/v1/modelzoo/tasks/openapi"
    BIZYAIR_POLL_INTERVAL_SECONDS = 5
    BIZYAIR_MAX_POLL_ATTEMPTS = 120
    
    def __init__(self, config: dict, core=None):
        """
        Initialize media service
        
        Args:
            config: Full application config dict
            core: PixelleVideoCore instance (for accessing shared ComfyKit)
        """
        super().__init__(config, service_name="image", core=core)  # Keep "image" for config compatibility
    
    def _scan_workflows(self):
        """
        Scan workflows for both image_ and video_ prefixes
        
        Override parent method to support multiple prefixes
        """
        from pathlib import Path

        from pixelle_video.utils.os_util import (
            get_resource_path,
            list_resource_dirs,
            list_resource_files,
        )
        
        workflows = []
        
        # Get all workflow source directories
        source_dirs = list_resource_dirs("workflows")
        
        if not source_dirs:
            logger.warning("No workflow source directories found")
            return workflows
        
        # Scan each source directory for workflow files
        for source_name in source_dirs:
            # Get all JSON files for this source
            workflow_files = list_resource_files("workflows", source_name)
            
            # Filter to only files matching image_ or video_ prefix
            matching_files = [
                f for f in workflow_files 
                if (f.startswith("image_") or f.startswith("video_")) and f.endswith('.json')
            ]
            
            for filename in matching_files:
                try:
                    # Get actual file path
                    file_path = Path(get_resource_path("workflows", source_name, filename))
                    workflow_info = self._parse_workflow_file(file_path, source_name)
                    workflows.append(workflow_info)
                    logger.debug(f"Found workflow: {workflow_info['key']}")
                except Exception as e:
                    logger.error(f"Failed to parse workflow {source_name}/{filename}: {e}")
        
        # Sort by key (source/name)
        return sorted(workflows, key=lambda w: w["key"])
    
    async def __call__(
        self,
        prompt: str,
        workflow: Optional[str] = None,
        # Media type specification (required for proper handling)
        media_type: str = "image",  # "image" or "video"
        # ComfyUI connection (optional overrides)
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        # Common workflow parameters
        width: Optional[int] = None,
        height: Optional[int] = None,
        duration: Optional[float] = None,  # Video duration in seconds (for video workflows)
        negative_prompt: Optional[str] = None,
        steps: Optional[int] = None,
        seed: Optional[int] = None,
        cfg: Optional[float] = None,
        sampler: Optional[str] = None,
        **params
    ) -> MediaResult:
        """
        Generate media (image or video) using workflow
        
        Media type must be specified explicitly via media_type parameter.
        Returns a MediaResult object containing media type and URL.
        
        Args:
            prompt: Media generation prompt
            workflow: Workflow filename (default: from config or "image_flux.json")
            media_type: Type of media to generate - "image" or "video" (default: "image")
            comfyui_url: ComfyUI URL (optional, overrides config)
            runninghub_api_key: RunningHub API key (optional, overrides config)
            width: Media width
            height: Media height
            duration: Target video duration in seconds (only for video workflows, typically from TTS audio duration)
            negative_prompt: Negative prompt
            steps: Sampling steps
            seed: Random seed
            cfg: CFG scale
            sampler: Sampler name
            **params: Additional workflow parameters
        
        Returns:
            MediaResult object with media_type ("image" or "video") and url
        
        Examples:
            # Simplest: use default workflow (workflows/image_flux.json)
            media = await pixelle_video.media(prompt="a beautiful cat")
            if media.is_image:
                print(f"Image: {media.url}")
            
            # Use specific workflow
            media = await pixelle_video.media(
                prompt="a cat",
                workflow="image_flux.json"
            )
            
            # Video workflow
            media = await pixelle_video.media(
                prompt="a cat running",
                workflow="image_video.json"
            )
            if media.is_video:
                print(f"Video: {media.url}, duration: {media.duration}s")
            
            # With additional parameters
            media = await pixelle_video.media(
                prompt="a cat",
                workflow="image_flux.json",
                width=1024,
                height=1024,
                steps=20,
                seed=42
            )
            
            # With absolute path
            media = await pixelle_video.media(
                prompt="a cat",
                workflow="/path/to/custom.json"
            )
            
            # With custom ComfyUI server
            media = await pixelle_video.media(
                prompt="a cat",
                comfyui_url="http://192.168.1.100:8188"
            )
        """
        if media_type == "image" and self._has_openai_image_generation_config():
            return await self._call_openai_image_generation(
                prompt=prompt,
                width=width,
                height=height,
                **params,
            )

        # 1. Resolve workflow (returns structured info)
        workflow_info = self._resolve_workflow(workflow=workflow)
        
        # 2. Build workflow parameters (ComfyKit config is now managed by core)
        workflow_params = {"prompt": prompt}
        
        # Add optional parameters
        if width is not None:
            workflow_params["width"] = width
        if height is not None:
            workflow_params["height"] = height
        if duration is not None:
            workflow_params["duration"] = duration
            if media_type == "video":
                logger.info(f"📏 Target video duration: {duration:.2f}s (from TTS audio)")
        if negative_prompt is not None:
            workflow_params["negative_prompt"] = negative_prompt
        if steps is not None:
            workflow_params["steps"] = steps
        if seed is not None:
            workflow_params["seed"] = seed
        if cfg is not None:
            workflow_params["cfg"] = cfg
        if sampler is not None:
            workflow_params["sampler"] = sampler
        
        # Add any additional parameters
        workflow_params.update(params)
        
        logger.debug(f"Workflow parameters: {workflow_params}")
        
        # 4. Execute workflow
        try:
            # BizyAir direct API (no ComfyUI needed)
            if workflow_info["source"] == "bizyair":
                return await self._call_bizyair_api(workflow_info, workflow_params)
            
            # Get shared ComfyKit instance (lazy initialization + config hot-reload)
            kit = await self.core._get_or_create_comfykit()
            
            # Determine what to pass to ComfyKit based on source
            if workflow_info["source"] == "runninghub" and "workflow_id" in workflow_info:
                # RunningHub: pass workflow_id (ComfyKit will use runninghub backend)
                workflow_input = workflow_info["workflow_id"]
                logger.info(f"Executing RunningHub workflow: {workflow_input}")
            else:
                # Selfhost: pass file path (ComfyKit will use local ComfyUI)
                workflow_input = workflow_info["path"]
                logger.info(f"Executing selfhost workflow: {workflow_input}")
            
            result = await kit.execute(workflow_input, workflow_params)
            
            # 5. Handle result based on specified media_type
            if result.status != "completed":
                error_msg = result.msg or "Unknown error"
                logger.error(f"Media generation failed: {error_msg}")
                raise Exception(f"Media generation failed: {error_msg}")
            
            # Extract media based on specified type
            if media_type == "video":
                # Video workflow - get video from result
                if not result.videos:
                    logger.error("No video generated (workflow returned no videos)")
                    raise Exception("No video generated")
                
                video_url = result.videos[0]
                logger.info(f"✅ Generated video: {video_url}")
                
                # Try to extract duration from result (if available)
                duration = None
                if hasattr(result, 'duration') and result.duration:
                    duration = result.duration
                
                return MediaResult(
                    media_type="video",
                    url=video_url,
                    duration=duration
                )
            else:  # image
                # Image workflow - get image from result
                if not result.images:
                    logger.error("No image generated (workflow returned no images)")
                    raise Exception("No image generated")
                
                image_url = result.images[0]
                logger.info(f"✅ Generated image: {image_url}")
                
                return MediaResult(
                    media_type="image",
                    url=image_url
                )
        
        except Exception as e:
            logger.error(f"Media generation error: {e}")
            raise

    def _get_openai_image_generation_config(self) -> dict[str, str]:
        config = config_manager.get_image_generation_config()
        return {
            "api_key": str(config.get("api_key") or os.getenv("IMAGE_GENERATION_API_KEY") or "").strip(),
            "base_url": str(config.get("base_url") or os.getenv("IMAGE_GENERATION_BASE_URL") or "").strip(),
            "model": str(config.get("model") or os.getenv("IMAGE_GENERATION_MODEL") or "").strip(),
        }

    def _has_openai_image_generation_config(self) -> bool:
        config = self._get_openai_image_generation_config()
        return bool(config["api_key"] and config["base_url"] and config["model"])

    async def _call_openai_image_generation(
        self,
        prompt: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        **params,
    ) -> MediaResult:
        config = self._get_openai_image_generation_config()
        if not (config["api_key"] and config["base_url"] and config["model"]):
            raise ValueError("Image generation API requires api_key, base_url, and model")

        size = params.get("size")
        if not size:
            final_width = int(width or 1024)
            final_height = int(height or 1024)
            size = f"{final_width}x{final_height}"

        base_url = config["base_url"].rstrip("/")
        payload: dict[str, Any] = {
            "model": config["model"],
            "prompt": prompt,
            "n": int(params.get("n") or 1),
            "size": size,
        }
        if "65535.space" in base_url:
            payload["official_fallback"] = False

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        submit_url = f"{base_url}/images/generations"
        logger.info(f"Submitting OpenAI-compatible image generation: model={config['model']}, size={size}")

        async with httpx.AsyncClient(timeout=params.get("image_generation_timeout", 120.0)) as client:
            response = await client.post(submit_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()

            image_ref = await self._extract_openai_image_result(
                client=client,
                base_url=base_url,
                response_data=result,
                headers=headers,
            )

        logger.info(f"✅ Generated image via configured image API: {image_ref}")
        return MediaResult(media_type="image", url=image_ref)

    async def _extract_openai_image_result(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        response_data: dict[str, Any],
        headers: dict[str, str],
    ) -> str:
        direct = self._extract_direct_image_result(response_data)
        if direct:
            return direct

        job_id = response_data.get("job_id") or response_data.get("task_id")
        nested_data = response_data.get("data")
        if isinstance(nested_data, dict):
            job_id = job_id or nested_data.get("job_id") or nested_data.get("task_id")
            status_url = nested_data.get("status_url")
        else:
            status_url = response_data.get("status_url")

        if not job_id:
            raise RuntimeError(f"Image generation response did not include image data or job_id: {response_data}")

        poll_url = self._normalize_openai_image_status_url(
            base_url=base_url,
            status_url=status_url,
            job_id=job_id,
        )
        return await self._poll_openai_image_job(client, poll_url, headers)

    def _normalize_openai_image_status_url(
        self,
        base_url: str,
        status_url: Optional[str],
        job_id: str,
    ) -> str:
        fallback_url = f"{base_url.rstrip('/')}/images/async-generations/{job_id}"
        if not status_url:
            return fallback_url

        candidate = str(status_url).strip()
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"}:
            return candidate

        base = base_url.rstrip("/")
        base_parts = urlparse(base)
        if candidate.startswith("//"):
            scheme = base_parts.scheme or "https"
            return f"{scheme}:{candidate}"

        if parsed.netloc or "." in candidate.split("/", 1)[0]:
            scheme = base_parts.scheme or "https"
            return f"{scheme}://{candidate.lstrip('/')}"

        if candidate.startswith("/"):
            origin = f"{base_parts.scheme}://{base_parts.netloc}"
            return urljoin(origin, candidate)

        return urljoin(f"{base}/", candidate)

    def _extract_direct_image_result(self, response_data: dict[str, Any]) -> Optional[str]:
        data = response_data.get("data")
        if isinstance(data, dict):
            nested = self._extract_direct_image_result(data)
            if nested:
                return nested
        if not isinstance(data, list) or not data:
            return None

        first = data[0]
        if not isinstance(first, dict):
            return None
        if first.get("url"):
            return str(first["url"])
        if first.get("b64_json"):
            return self._save_base64_image(str(first["b64_json"]))
        return None

    async def _poll_openai_image_job(
        self,
        client: httpx.AsyncClient,
        poll_url: str,
        headers: dict[str, str],
    ) -> str:
        deadline = asyncio.get_running_loop().time() + 600
        auth_headers = {"Authorization": headers["Authorization"]}
        while asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(2)
            response = await client.get(poll_url, headers=auth_headers)
            response.raise_for_status()
            data = response.json()
            job = data.get("data") if isinstance(data.get("data"), dict) else data
            status = job.get("status")

            if status == "done":
                urls = job.get("result_urls") or []
                if urls:
                    return str(urls[0])
                b64_values = job.get("result_b64") or []
                if b64_values:
                    return self._save_base64_image(str(b64_values[0]))
                raise RuntimeError("Image generation job completed without result_urls or result_b64")
            if status == "failed":
                raise RuntimeError(job.get("error_message") or job.get("error_code") or "Image generation job failed")

        raise TimeoutError("Image generation job timed out after 600 seconds")

    def _save_base64_image(self, b64_json: str) -> str:
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{uuid.uuid4().hex}.png"
        output_path.write_bytes(base64.b64decode(b64_json))
        return str(output_path)
    
    async def _call_bizyair_api(self, workflow_info: dict, workflow_params: dict) -> MediaResult:
        bizyair_api_key = self._get_bizyair_api_key()
        endpoint = workflow_info.get("endpoint")
        api_type = workflow_info.get("api_type", "modelzoo")

        if api_type != "modelzoo":
            raise ValueError(
                f"Unsupported BizyAir api_type '{api_type}'. Only 'modelzoo' is supported."
            )
        if not endpoint:
            raise ValueError("BizyAir workflow missing 'endpoint' in workflow file")

        payload = self._build_bizyair_payload(workflow_info, workflow_params)
        submit_url = f"{self.BIZYAIR_API_BASE}/{endpoint}"
        headers = {
            "Authorization": f"Bearer {bizyair_api_key}",
            "Content-Type": "application/json",
            "X-BizyAir-Log-Mask-Fields": "prompt",
        }

        logger.info(f"Submitting BizyAir Model Zoo task: endpoint={endpoint}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(submit_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()

        logger.debug(f"BizyAir submit response: {result}")

        submit_data = self._unwrap_bizyair_response(result)
        request_id = submit_data.get("request_id")

        if not request_id:
            raise RuntimeError(f"BizyAir did not return a request_id. Response: {result}")

        logger.info(f"BizyAir task {request_id}: polling for result...")
        return await self._poll_bizyair_result(request_id, bizyair_api_key)
    
    def _get_bizyair_api_key(self) -> str:
        bizyair_api_key = self.global_config.get("bizyair_api_key") or os.getenv("BIZYAIR_API_KEY")
        if not bizyair_api_key or not str(bizyair_api_key).strip():
            raise ValueError(
                "BizyAir API key not configured. "
                "Please set 'bizyair_api_key' in config.yaml under 'comfyui' section "
                "or set the BIZYAIR_API_KEY environment variable."
            )
        return str(bizyair_api_key).strip()

    def _unwrap_bizyair_response(self, response_data: dict[str, Any]) -> dict[str, Any]:
        data = response_data.get("data")
        if isinstance(data, dict):
            return data
        return response_data

    def _build_bizyair_payload(self, workflow_info: dict, workflow_params: dict) -> dict[str, Any]:
        payload = {"quality": "medium", **(workflow_info.get("defaults") or {})}

        for param_name in ("prompt", "width", "height", "quality"):
            if param_name in workflow_params and workflow_params[param_name] is not None:
                payload[param_name] = workflow_params[param_name]

        if not payload.get("prompt"):
            raise ValueError("BizyAir prompt is required")

        width = payload.get("width")
        height = payload.get("height")
        if width is None or height is None:
            raise ValueError("BizyAir workflow requires both width and height")

        payload["width"] = int(width)
        payload["height"] = int(height)
        self._validate_bizyair_dimensions(payload["width"], payload["height"])

        if payload.get("quality") not in {"low", "medium", "high"}:
            raise ValueError("BizyAir quality must be one of: low, medium, high")

        return payload

    def _validate_bizyair_dimensions(self, width: int, height: int) -> None:
        if not (480 <= width <= 3840 and 480 <= height <= 3840):
            raise ValueError("BizyAir width and height must be between 480 and 3840")

        if not self._is_bizyair_dimension_step_aligned(width, height):
            raise ValueError("BizyAir width and height must be multiples of 16")

        aspect_ratio = max(width, height) / min(width, height)
        if aspect_ratio > 3:
            raise ValueError("BizyAir aspect ratio must be no greater than 3:1")

        total_pixels = width * height
        if not (655360 <= total_pixels <= 8294400):
            raise ValueError("BizyAir total pixels must be between 655360 and 8294400")

    def _is_bizyair_dimension_step_aligned(self, width: int, height: int) -> bool:
        official_example_axes = {1080}
        return all(dimension % 16 == 0 or dimension in official_example_axes for dimension in (width, height))

    def _extract_bizyair_image_url(self, outputs: dict[str, Any] | None) -> Optional[str]:
        if not outputs:
            return None
        images = outputs.get("images") or []
        return images[0] if images else None
    
    async def _poll_bizyair_result(self, request_id: str, api_key: str) -> MediaResult:
        headers = {"Authorization": f"Bearer {api_key}"}
        poll_url = f"{self.BIZYAIR_API_BASE}/{request_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(self.BIZYAIR_MAX_POLL_ATTEMPTS):
                if attempt > 0:
                    await asyncio.sleep(self.BIZYAIR_POLL_INTERVAL_SECONDS)

                resp = await client.get(poll_url, headers=headers)
                resp.raise_for_status()
                detail = resp.json()

                logger.debug(f"BizyAir poll [{attempt+1}]: {detail}")
                task_data = self._unwrap_bizyair_response(detail)

                status = task_data.get("status", "Unknown")

                if status == "Success":
                    image_url = self._extract_bizyair_image_url(task_data.get("outputs"))
                    if not image_url:
                        raise RuntimeError("BizyAir returned no image URL in outputs")
                    logger.info(f"Generated BizyAir image: {image_url}")
                    return MediaResult(media_type="image", url=image_url)

                if status == "Failed":
                    message = task_data.get("message") or f"BizyAir task {request_id} failed"
                    raise RuntimeError(f"BizyAir task {request_id} failed: {message}")

                if status not in ("Pending", "Running", "Saving"):
                    logger.warning(
                        f"BizyAir task {request_id}: unknown status={status}, continuing to poll"
                    )
                    continue

                if attempt > 0 and attempt % 12 == 0:
                    elapsed = attempt * self.BIZYAIR_POLL_INTERVAL_SECONDS
                    logger.info(f"BizyAir task {request_id}: still {status} after {elapsed}s")

        timeout_seconds = self.BIZYAIR_MAX_POLL_ATTEMPTS * self.BIZYAIR_POLL_INTERVAL_SECONDS
        raise TimeoutError(f"BizyAir task {request_id} timed out after {timeout_seconds}s")
