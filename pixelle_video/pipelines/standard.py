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
Standard Video Generation Pipeline

Standard workflow for generating short videos from topic or fixed script.
This is the default pipeline for general-purpose video generation.
Refactored to use LinearVideoPipeline (Template Method Pattern).
"""

import asyncio
import copy
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from pixelle_video.models.progress import ProgressEvent
from pixelle_video.models.storyboard import (
    Storyboard,
    StoryboardConfig,
    StoryboardFrame,
    VideoGenerationResult,
)
from pixelle_video.pipelines.linear import LinearVideoPipeline, PipelineContext
from pixelle_video.services.video import VideoService
from pixelle_video.utils.content_generators import (
    generate_image_prompts,
    generate_narrations_from_topic,
    generate_title,
    split_narration_script,
)
from pixelle_video.utils.os_util import create_task_output_dir, get_task_final_video_path
from pixelle_video.utils.prompt_helper import (
    build_image_prompt,
    is_visual_prompt_same_as_narration,
)
from pixelle_video.utils.template_util import get_template_type


class StandardPipeline(LinearVideoPipeline):
    """
    Standard video generation pipeline
    
    Workflow:
    1. Generate/determine title
    2. Generate narrations (from topic or split fixed script)
    3. Generate image prompts for each narration
    4. For each frame:
       - Generate audio (TTS)
       - Generate image
       - Compose frame with template
       - Create video segment
    5. Concatenate all segments
    6. Add BGM (optional)
    
    Supports two modes:
    - "generate": LLM generates narrations from topic
    - "fixed": Use provided script as-is (each line = one narration)
    """
    
    # ==================== Lifecycle Methods ====================

    _ASSET_REUSE_INPUT_KEYS = (
        "scenes",
        "tts_inference_mode",
        "tts_voice",
        "tts_speed",
        "tts_workflow",
        "ref_audio",
        "minimax_model",
        "minimax_emotion",
        "media_width",
        "media_height",
        "media_workflow",
        "prompt_prefix",
        "composition_mode",
        "image_motion_enabled",
        "image_motion_mode",
        "image_motion_strength",
        "image_fit_mode",
        "video_fps",
    )

    @staticmethod
    def _normalize_reuse_value(key: str, value: Any) -> Any:
        if key != "scenes":
            return value
        return [
            {
                "narration": str(scene.get("narration") or "").strip(),
                "visual_prompt": str(scene.get("visual_prompt") or "").strip(),
            }
            for scene in (value or [])
        ]

    @staticmethod
    def _asset_exists(path: str | None) -> bool:
        if not path:
            return False
        try:
            asset = Path(path)
            return asset.is_file() and asset.stat().st_size > 0
        except OSError:
            return False

    async def _load_reusable_storyboard(
        self,
        ctx: PipelineContext,
        source_task_id: str,
    ) -> tuple[Storyboard | None, str | None]:
        metadata = await self.core.persistence.load_task_metadata(source_task_id)
        source = await self.core.persistence.load_storyboard(source_task_id)
        if not metadata or metadata.get("status") != "completed":
            return None, "source task is not completed"
        if not source or not source.frames:
            return None, "source storyboard is unavailable"
        if source.config.composition_mode != "plain_image":
            return None, "source task is not an image-motion composition"

        source_input = metadata.get("input") or {}
        for key in self._ASSET_REUSE_INPUT_KEYS:
            source_value = self._normalize_reuse_value(key, source_input.get(key))
            requested_value = self._normalize_reuse_value(key, ctx.params.get(key))
            if source_value != requested_value:
                return None, f"production input changed: {key}"

        for frame in source.frames:
            if not self._asset_exists(frame.audio_path):
                return None, f"source audio is unavailable for frame {frame.index + 1}"
            media_path = frame.image_path or frame.video_path
            if not self._asset_exists(media_path):
                return None, f"source media is unavailable for frame {frame.index + 1}"

        return copy.deepcopy(source), None

    async def setup_environment(self, ctx: PipelineContext):
        """Step 1: Setup task directory and environment."""
        text = ctx.input_text
        mode = ctx.params.get("mode", "generate")
        resume_task_id = ctx.params.get("resume_task_id")
        
        logger.info(f"🚀 Starting StandardPipeline in '{mode}' mode")
        logger.info(f"   Text length: {len(text)} chars")

        if resume_task_id:
            storyboard = await self.core.persistence.load_storyboard(resume_task_id)
            if not storyboard:
                raise ValueError(f"Cannot resume task {resume_task_id}: storyboard not found")

            ctx.params["resume"] = True
            ctx.task_id = resume_task_id
            ctx.task_dir, _ = create_task_output_dir(resume_task_id)
            ctx.final_video_path = get_task_final_video_path(resume_task_id)
            ctx.storyboard = storyboard
            ctx.config = storyboard.config
            ctx.config.task_id = resume_task_id
            ctx.title = storyboard.title
            ctx.narrations = [frame.narration for frame in storyboard.frames]
            ctx.image_prompts = [frame.image_prompt for frame in storyboard.frames]
            storyboard.final_video_path = ctx.final_video_path

            logger.info(f"♻️  Resuming task: {resume_task_id}")
            await self._persist_running_task_data(ctx)
            return

        source_task_id = ctx.params.get("reuse_assets_from_task_id")
        reusable_storyboard = None
        if ctx.params.get("existing_scene_assets"):
            ctx.params["asset_reuse"] = True
            ctx.title = ctx.params.get("title") or text
            explicit_scenes = ctx.params.get("scenes") or []
            ctx.narrations = [
                str(scene.get("narration") or "").strip()
                for scene in explicit_scenes
                if str(scene.get("narration") or "").strip()
            ]
            ctx.image_prompts = [
                str(scene.get("visual_prompt") or "").strip()
                for scene in explicit_scenes
            ]
            task_dir, task_id = create_task_output_dir(ctx.params.get("task_id"))
            ctx.task_id = task_id
            ctx.task_dir = task_dir
            ctx.final_video_path = get_task_final_video_path(task_id)
            logger.info("♻️ Reusing project-local workbench assets")
            await self._persist_running_task_data(ctx)
            return
        if source_task_id:
            ctx.params["asset_reuse"] = False
            reusable_storyboard, fallback_reason = await self._load_reusable_storyboard(
                ctx,
                source_task_id,
            )
            if fallback_reason:
                ctx.params["asset_reuse_fallback_reason"] = fallback_reason
                logger.info(
                    "Asset reuse skipped for task {}: {}",
                    source_task_id,
                    fallback_reason,
                )
        
        # Create isolated task directory
        task_dir, task_id = create_task_output_dir(ctx.params.get("task_id"))
        ctx.task_id = task_id
        ctx.task_dir = task_dir
        
        logger.info(f"📁 Task directory created: {task_dir}")
        logger.info(f"   Task ID: {task_id}")
        
        # Determine final video path
        output_path = ctx.params.get("output_path")
        if output_path is None:
            ctx.final_video_path = get_task_final_video_path(task_id)
        else:
            # We will copy to this path in finalize/post_production
            # For internal processing, we still use the task dir path? 
            # Actually StandardPipeline logic used get_task_final_video_path as the target for concat
            # and then copied. Let's stick to that.
            ctx.final_video_path = get_task_final_video_path(task_id)
            logger.info(f"   Will copy final video to: {output_path}")

        if reusable_storyboard:
            ctx.params["asset_reuse"] = True
            ctx.params["reused_assets_from_task_id"] = source_task_id
            ctx.params.pop("asset_reuse_fallback_reason", None)
            ctx.storyboard = reusable_storyboard
            ctx.config = reusable_storyboard.config
            ctx.config.task_id = task_id
            ctx.config.subtitle_enabled = ctx.params.get("subtitle_enabled", True)
            ctx.config.subtitle_style = ctx.params.get("subtitle_style")
            ctx.storyboard.title = ctx.params.get("title") or reusable_storyboard.title
            ctx.storyboard.final_video_path = ctx.final_video_path
            ctx.storyboard.total_duration = 0.0
            ctx.storyboard.completed_at = None
            ctx.title = ctx.storyboard.title
            ctx.narrations = [frame.narration for frame in ctx.storyboard.frames]
            ctx.image_prompts = [frame.image_prompt for frame in ctx.storyboard.frames]

            for frame in ctx.storyboard.frames:
                frame.composed_image_path = None
                frame.video_segment_path = None
                frame.status = "pending"
                frame.completed_steps = {
                    "audio": True,
                    "media": True,
                    "compose": False,
                    "segment": False,
                }
                frame.errors = {}

            logger.info(
                "Reusing narration audio and media from task {} for subtitle rerender",
                source_task_id,
            )
            self._report_progress(
                ctx.progress_callback,
                "reusing_audio_and_media",
                0.03,
                extra_info=f"source_task_id={source_task_id}",
            )
            await self._persist_running_task_data(ctx)
            return

        await self._persist_running_task_data(ctx)

    async def generate_content(self, ctx: PipelineContext):
        """Step 2: Generate or process script/narrations."""
        if (ctx.params.get("resume") or ctx.params.get("asset_reuse")) and ctx.narrations:
            logger.info("♻️  Reusing saved narrations")
            return

        mode = ctx.params.get("mode", "generate")
        text = ctx.input_text
        n_scenes = ctx.params.get("n_scenes", 5)
        min_words = ctx.params.get("min_narration_words", 5)
        max_words = ctx.params.get("max_narration_words", 20)
        
        explicit_scenes = ctx.params.get("scenes") or []
        if explicit_scenes:
            self._report_progress(ctx.progress_callback, "loading_scenes", 0.05)
            ctx.narrations = [
                str(scene.get("narration", "")).strip()
                for scene in explicit_scenes
                if str(scene.get("narration", "")).strip()
            ]
            logger.info(f"✅ Loaded {len(ctx.narrations)} explicit scene narrations")
        elif mode == "generate":
            self._report_progress(ctx.progress_callback, "generating_narrations", 0.05)
            ctx.narrations = await generate_narrations_from_topic(
                self.llm,
                topic=text,
                n_scenes=n_scenes,
                min_words=min_words,
                max_words=max_words
            )
            logger.info(f"✅ Generated {len(ctx.narrations)} narrations")
        else:  # fixed
            self._report_progress(ctx.progress_callback, "splitting_script", 0.05)
            split_mode = ctx.params.get("split_mode", "auto")
            ctx.narrations = await split_narration_script(text, split_mode=split_mode)
            logger.info(f"✅ Split script into {len(ctx.narrations)} segments (mode={split_mode})")
            logger.info(f"   Note: n_scenes={n_scenes} is ignored in fixed mode")
        await self._persist_running_task_data(ctx)

    async def determine_title(self, ctx: PipelineContext):
        """Step 3: Determine or generate video title."""
        if (ctx.params.get("resume") or ctx.params.get("asset_reuse")) and ctx.title:
            logger.info("♻️  Reusing saved title")
            return

        # Note: Swapped order with generate_content in base class call, 
        # but in StandardPipeline original code, title was determined BEFORE narrations.
        # However, LinearVideoPipeline defines generate_content BEFORE determine_title.
        # This is fine as they are independent in StandardPipeline logic.
        
        title = ctx.params.get("title")
        mode = ctx.params.get("mode", "generate")
        text = ctx.input_text
        
        if title:
            ctx.title = title
            logger.info(f"   Title: '{title}' (user-specified)")
        else:
            self._report_progress(ctx.progress_callback, "generating_title", 0.01)
            if mode == "generate":
                ctx.title = await generate_title(self.llm, text, strategy="auto")
                logger.info(f"   Title: '{ctx.title}' (auto-generated)")
            else:  # fixed
                ctx.title = await generate_title(self.llm, text, strategy="llm")
                logger.info(f"   Title: '{ctx.title}' (LLM-generated)")
        await self._persist_running_task_data(ctx)

    async def plan_visuals(self, ctx: PipelineContext):
        """Step 4: Generate image prompts or visual descriptions."""
        if (ctx.params.get("resume") or ctx.params.get("asset_reuse")) and ctx.image_prompts:
            logger.info("♻️  Reusing saved image prompts")
            return

        # Detect template type to determine if media generation is needed
        composition_mode = ctx.params.get("composition_mode", "template")
        pure_image_mode = composition_mode == "plain_image"
        frame_template = ctx.params.get("frame_template") or "1080x1920/default.html"
        
        template_name = Path(frame_template).name
        template_type = get_template_type(template_name)
        template_requires_media = pure_image_mode or (template_type in ["image", "video"])
        
        if pure_image_mode:
            logger.info("📸 Pure image mode requires image generation")
        elif template_type == "image":
            logger.info("📸 Template requires image generation")
        elif template_type == "video":
            logger.info("🎬 Template requires video generation")
        else:  # static
            logger.info("⚡ Static template - skipping media generation pipeline")
            logger.info("   💡 Benefits: Faster generation + Lower cost + No ComfyUI dependency")
        
        # Only generate image prompts if template requires media
        if template_requires_media:
            self._report_progress(ctx.progress_callback, "generating_image_prompts", 0.15)
            
            prompt_prefix = ctx.params.get("prompt_prefix")
            min_words = ctx.params.get("min_image_prompt_words", 30)
            max_words = ctx.params.get("max_image_prompt_words", 60)
            
            # Override prompt_prefix if provided
            image_config = self.core.config.get("comfyui", {}).get("image", {})
            original_prefix = None
            if prompt_prefix is not None:
                original_prefix = image_config.get("prompt_prefix")
                image_config["prompt_prefix"] = prompt_prefix
                logger.info(f"Using custom prompt_prefix: '{prompt_prefix}'")
            
            try:
                # Create progress callback wrapper for image prompt generation
                def image_prompt_progress(completed: int, total: int, message: str):
                    batch_progress = completed / total if total > 0 else 0
                    overall_progress = 0.15 + (batch_progress * 0.15)
                    self._report_progress(
                        ctx.progress_callback,
                        "generating_image_prompts",
                        overall_progress,
                        extra_info=message
                    )
                
                explicit_scenes = ctx.params.get("scenes") or []
                # Keep semantic metadata aligned with the filtered narration list.
                # Empty client rows must not shift focus/anchor hints to the next shot.
                semantic_scenes = [
                    scene for scene in explicit_scenes
                    if str(scene.get("narration") or "").strip()
                ]
                provided_prompts = [
                    ""
                    if index < len(ctx.narrations)
                    and is_visual_prompt_same_as_narration(
                        semantic_scenes[index].get("visual_prompt"),
                        ctx.narrations[index],
                    )
                    else str(semantic_scenes[index].get("visual_prompt") or "").strip()
                    for index in range(min(len(semantic_scenes), len(ctx.narrations)))
                ]
                if len(provided_prompts) < len(ctx.narrations):
                    provided_prompts.extend([""] * (len(ctx.narrations) - len(provided_prompts)))

                missing_indices = [
                    index for index, prompt in enumerate(provided_prompts[: len(ctx.narrations)])
                    if not prompt
                ]
                generated_prompts = []
                style_prefix_for_llm = (
                    prompt_prefix
                    if prompt_prefix is not None
                    else image_config.get("prompt_prefix", "")
                )
                if missing_indices:
                    generated_prompts = await generate_image_prompts(
                        self.llm,
                        narrations=[ctx.narrations[index] for index in missing_indices],
                        min_words=min_words,
                        max_words=max_words,
                        style_prefix=style_prefix_for_llm,
                        visual_focuses=[
                            str(semantic_scenes[index].get("visual_focus") or "").strip()
                            for index in missing_indices
                        ],
                        text_anchors=[
                            [str(value).strip() for value in (semantic_scenes[index].get("text_anchors") or []) if str(value).strip()]
                            for index in missing_indices
                        ],
                        progress_callback=image_prompt_progress,
                    )

                generated_by_index = dict(zip(missing_indices, generated_prompts))
                base_image_prompts = [
                    provided_prompts[index] or generated_by_index[index]
                    for index in range(len(ctx.narrations))
                ]
                
                # Apply prompt prefix
                image_config = self.core.config.get("comfyui", {}).get("image", {})
                prompt_prefix_to_use = prompt_prefix if prompt_prefix is not None else image_config.get("prompt_prefix", "")
                
                ctx.image_prompts = []
                for base_prompt in base_image_prompts:
                    final_prompt = build_image_prompt(base_prompt, prompt_prefix_to_use)
                    ctx.image_prompts.append(final_prompt)
                
            finally:
                # Restore original prompt_prefix
                if original_prefix is not None:
                    image_config["prompt_prefix"] = original_prefix
            
            logger.info(f"✅ Generated {len(ctx.image_prompts)} image prompts")
        else:
            # Static template - skip image prompt generation entirely
            ctx.image_prompts = [None] * len(ctx.narrations)
            logger.info("⚡ Skipped image prompt generation (static template)")
            logger.info(f"   💡 Savings: {len(ctx.narrations)} LLM calls + {len(ctx.narrations)} media generations")
        await self._persist_running_task_data(ctx)

    async def initialize_storyboard(self, ctx: PipelineContext):
        """Step 5: Create Storyboard object and frames."""
        if (ctx.params.get("resume") or ctx.params.get("asset_reuse")) and ctx.storyboard:
            ctx.config = ctx.storyboard.config
            ctx.config.task_id = ctx.task_id
            logger.info("♻️  Reusing saved storyboard")
            return

        # === Handle TTS parameter compatibility ===
        tts_inference_mode = ctx.params.get("tts_inference_mode")
        tts_voice = ctx.params.get("tts_voice")
        voice_id = ctx.params.get("voice_id")
        tts_workflow = ctx.params.get("tts_workflow")
        
        final_voice_id = None
        final_tts_workflow = tts_workflow
        
        if tts_inference_mode:
            # New API from web UI
            if tts_inference_mode == "local":
                final_voice_id = tts_voice or "zh-CN-YunjianNeural"
                final_tts_workflow = None
                logger.debug(f"TTS Mode: local (voice={final_voice_id})")
            elif tts_inference_mode == "comfyui":
                final_voice_id = None
                logger.debug(f"TTS Mode: comfyui (workflow={final_tts_workflow})")
            elif tts_inference_mode == "minimax":
                final_voice_id = tts_voice or "male-qn-qingse"
                final_tts_workflow = None
                logger.debug(f"TTS Mode: minimax (voice={final_voice_id})")
            elif tts_inference_mode == "mimo":
                final_voice_id = tts_voice or "mimo_default"
                final_tts_workflow = None
                logger.debug(f"TTS Mode: mimo (voice={final_voice_id})")
            elif tts_inference_mode == "qwen_audio":
                final_voice_id = tts_voice or "Cherry"
                final_tts_workflow = None
                logger.debug(f"TTS Mode: qwen_audio (voice={final_voice_id})")
        else:
            # Old API
            final_voice_id = voice_id or tts_voice or "zh-CN-YunjianNeural"
            logger.debug(f"TTS Mode: legacy (voice_id={final_voice_id}, workflow={final_tts_workflow})")
            
        # Create config
        ctx.config = StoryboardConfig(
            task_id=ctx.task_id,
            n_storyboard=len(ctx.narrations), # Use actual length
            min_narration_words=ctx.params.get("min_narration_words", 5),
            max_narration_words=ctx.params.get("max_narration_words", 20),
            min_image_prompt_words=ctx.params.get("min_image_prompt_words", 30),
            max_image_prompt_words=ctx.params.get("max_image_prompt_words", 60),
            video_fps=ctx.params.get("video_fps", 30),
            tts_inference_mode=tts_inference_mode or "local",
            voice_id=final_voice_id,
            tts_workflow=final_tts_workflow,
            tts_speed=ctx.params.get("tts_speed", 1.2),
            ref_audio=ctx.params.get("ref_audio"),
            minimax_model=ctx.params.get("minimax_model"),
            minimax_emotion=ctx.params.get("minimax_emotion"),
            mimo_model=ctx.params.get("mimo_model"),
            mimo_style=ctx.params.get("mimo_style"),
            qwen_audio_model=ctx.params.get("qwen_audio_model"),
            qwen_audio_mode=ctx.params.get("qwen_audio_mode"),
            qwen_audio_instruction=ctx.params.get("qwen_audio_instruction"),
            qwen_audio_ref_audio=ctx.params.get("qwen_audio_ref_audio"),
            media_width=ctx.params.get("media_width"),
            media_height=ctx.params.get("media_height"),
            media_workflow=ctx.params.get("media_workflow"),
            frame_template=ctx.params.get("frame_template") or "1080x1920/default.html",
            template_params=ctx.params.get("template_params"),
            composition_mode=ctx.params.get("composition_mode", "template"),
            image_motion_enabled=ctx.params.get("image_motion_enabled", False),
            subtitle_enabled=ctx.params.get("subtitle_enabled", True),
            subtitle_style=ctx.params.get("subtitle_style"),
            image_motion_mode=ctx.params.get("image_motion_mode", "auto"),
            image_motion_strength=ctx.params.get("image_motion_strength", "subtle"),
            image_fit_mode=ctx.params.get("image_fit_mode", "cover"),
            use_api_image=bool(
                ctx.params.get("use_api_image", ctx.params.get("useApiImage", False))
            ),
        )
        
        # Create storyboard
        ctx.storyboard = Storyboard(
            title=ctx.title,
            config=ctx.config,
            content_metadata=ctx.params.get("content_metadata"),
            created_at=datetime.now()
        )
        
        # Create frames
        for i, (narration, image_prompt) in enumerate(zip(ctx.narrations, ctx.image_prompts)):
            frame = StoryboardFrame(
                index=i,
                narration=narration,
                image_prompt=image_prompt,
                created_at=datetime.now()
            )
            existing = (ctx.params.get("existing_scene_assets") or {}).get(
                (ctx.params.get("scenes") or [])[i].get("sceneId") if i < len(ctx.params.get("scenes") or []) else str(i),
                {},
            )
            if existing.get("audio_path"):
                frame.audio_path = existing["audio_path"]
            if existing.get("image_path"):
                frame.image_path = existing["image_path"]
                frame.media_type = "image"
            frame.duration = max(0.0, float(existing.get("duration_seconds") or 0)) + max(
                0.0,
                float(existing.get("manual_hold_seconds") or 0),
            )
            frame.completed_steps["audio"] = bool(frame.audio_path)
            frame.completed_steps["media"] = bool(frame.image_path)
            ctx.storyboard.frames.append(frame)
        await self._persist_running_task_data(ctx)

    async def produce_assets(self, ctx: PipelineContext):
        """Step 6: Generate audio, images, and render frames (Core processing)."""
        storyboard = ctx.storyboard
        config = ctx.config
        storyboard.total_duration = 0.0
        
        # Check if using RunningHub workflows for parallel processing
        is_runninghub = (
            (config.tts_workflow and config.tts_workflow.startswith("runninghub/")) or
            (config.media_workflow and config.media_workflow.startswith("runninghub/"))
        )
        
        # Get concurrent limit from config_manager (supports hot reload without restart)
        from pixelle_video.config import config_manager
        runninghub_concurrent_limit = config_manager.config.comfyui.runninghub_concurrent_limit or 1
        
        if is_runninghub and runninghub_concurrent_limit > 1:
            logger.info(f"🚀 Using parallel processing for RunningHub workflows (max {runninghub_concurrent_limit} concurrent)")
            
            semaphore = asyncio.Semaphore(runninghub_concurrent_limit)
            completed_count = 0
            
            async def process_frame_with_semaphore(i: int, frame: StoryboardFrame):
                nonlocal completed_count
                async with semaphore:
                    ctx.current_stage = "frame_processing"
                    ctx.current_frame_index = i
                    base_progress = 0.2
                    frame_range = 0.6
                    per_frame_progress = frame_range / len(storyboard.frames)
                    
                    # Create frame-specific progress callback
                    def frame_progress_callback(event: ProgressEvent):
                        overall_progress = base_progress + (per_frame_progress * completed_count) + (per_frame_progress * event.progress)
                        if ctx.progress_callback:
                            adjusted_event = ProgressEvent(
                                event_type=event.event_type,
                                progress=overall_progress,
                                frame_current=i+1,
                                frame_total=len(storyboard.frames),
                                step=event.step,
                                action=event.action
                            )
                            ctx.progress_callback(adjusted_event)
                    
                    # Report frame start
                    self._report_progress(
                        ctx.progress_callback,
                        "processing_frame",
                        base_progress + (per_frame_progress * completed_count),
                        frame_current=i+1,
                        frame_total=len(storyboard.frames)
                    )
                    
                    processed_frame = await self.core.frame_processor(
                        frame=frame,
                        storyboard=storyboard,
                        config=config,
                        total_frames=len(storyboard.frames),
                        progress_callback=frame_progress_callback
                    )
                    
                    completed_count += 1
                    await self._persist_running_task_data(ctx)
                    logger.info(f"✅ Frame {i+1} completed ({processed_frame.duration:.2f}s) [{completed_count}/{len(storyboard.frames)}]")
                    return i, processed_frame
            
            # Create all tasks and execute in parallel
            tasks = [process_frame_with_semaphore(i, frame) for i, frame in enumerate(storyboard.frames)]
            results = await asyncio.gather(*tasks)
            
            # Update frames in order and calculate total duration
            for idx, processed_frame in sorted(results, key=lambda x: x[0]):
                storyboard.frames[idx] = processed_frame
                storyboard.total_duration += processed_frame.duration
            
            logger.info(f"✅ All frames processed in parallel (total duration: {storyboard.total_duration:.2f}s)")
        else:
            # Serial processing for non-RunningHub workflows
            logger.info("⚙️ Using serial processing (non-RunningHub workflow)")
            
            for i, frame in enumerate(storyboard.frames):
                ctx.current_stage = "frame_processing"
                ctx.current_frame_index = i
                base_progress = 0.2
                frame_range = 0.6
                per_frame_progress = frame_range / len(storyboard.frames)
                
                # Create frame-specific progress callback
                def frame_progress_callback(event: ProgressEvent):
                    overall_progress = base_progress + (per_frame_progress * i) + (per_frame_progress * event.progress)
                    if ctx.progress_callback:
                        adjusted_event = ProgressEvent(
                            event_type=event.event_type,
                            progress=overall_progress,
                            frame_current=event.frame_current,
                            frame_total=event.frame_total,
                            step=event.step,
                            action=event.action
                        )
                        ctx.progress_callback(adjusted_event)
                
                # Report frame start
                self._report_progress(
                    ctx.progress_callback,
                    "processing_frame",
                    base_progress + (per_frame_progress * i),
                    frame_current=i+1,
                    frame_total=len(storyboard.frames)
                )
                
                processed_frame = await self.core.frame_processor(
                    frame=frame,
                    storyboard=storyboard,
                    config=config,
                    total_frames=len(storyboard.frames),
                    progress_callback=frame_progress_callback
                )
                storyboard.total_duration += processed_frame.duration
                await self._persist_running_task_data(ctx)
                logger.info(f"✅ Frame {i+1} completed ({processed_frame.duration:.2f}s)")

    async def post_production(self, ctx: PipelineContext):
        """Step 7: Concatenate videos, apply intro/outro bookends, and add BGM."""
        self._report_progress(ctx.progress_callback, "concatenating", 0.85)

        storyboard = ctx.storyboard
        segment_paths = [frame.video_segment_path for frame in storyboard.frames]
        speech_audios = [frame.audio_path for frame in storyboard.frames]
        use_gapless_speech = bool(ctx.params.get("continuous_av_hold_split"))
        final_output = ctx.final_video_path
        bgm_path = ctx.params.get("bgm_path")
        bgm_volume = ctx.params.get("bgm_volume", 0.2)
        bgm_mode = ctx.params.get("bgm_mode", "loop")
        params = dict(ctx.params or {})

        def _run_post_production() -> str:
            """CPU-bound FFmpeg post path — runs in a worker thread."""
            video_service = VideoService()
            from pixelle_video.utils.bookend import normalize_bookend_config

            bookend = params.get("bookend")
            if not isinstance(bookend, dict):
                bookend = normalize_bookend_config(params)
            else:
                bookend = normalize_bookend_config({**params, **bookend})

            # Continuous TTS / workbench: rebuild speech from pure narration clips,
            # padding each clip to its segment duration so manual holds become
            # inter-clip silence (same as workbench preview). Missing speech must
            # fail hard — silent fallback looks like a "success" bug.
            if use_gapless_speech:
                missing = [
                    index
                    for index, path in enumerate(speech_audios)
                    if not path or not Path(path).is_file()
                ]
                if missing:
                    raise ValueError(
                        "continuous_av_hold_split requires speech audio for every scene; "
                        f"missing or unreadable audio at frame index(es): {missing}"
                    )
                logger.info(
                    "Using timeline-aligned speech mux (preview hold parity) for {} segments",
                    len(segment_paths),
                )
                return video_service.concat_videos_gapless_speech(
                    video_segments=segment_paths,
                    speech_audios=speech_audios,
                    output=final_output,
                    bgm_path=bgm_path,
                    bgm_volume=bgm_volume,
                    bgm_mode=bgm_mode,
                    bookend=bookend,
                )

            return video_service.concat_videos(
                videos=segment_paths,
                output=final_output,
                bgm_path=bgm_path,
                bgm_volume=bgm_volume,
                bgm_mode=bgm_mode,
                bookend=bookend,
            )

        # Off the event loop so export progress polling stays responsive.
        final_video_path = await asyncio.to_thread(_run_post_production)

        storyboard.final_video_path = final_video_path
        storyboard.completed_at = datetime.now()

        # Copy to user-specified path if provided
        user_specified_output = ctx.params.get("output_path")
        if user_specified_output:
            Path(user_specified_output).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(final_video_path, user_specified_output)
            logger.info(f"📹 Final video copied to: {user_specified_output}")
            ctx.final_video_path = user_specified_output
            storyboard.final_video_path = user_specified_output

        logger.success(f"🎬 Video generation completed: {ctx.final_video_path}")

    async def finalize(self, ctx: PipelineContext) -> VideoGenerationResult:
        """Step 8: Create result object and persist metadata."""
        self._report_progress(ctx.progress_callback, "completed", 1.0)
        
        video_path_obj = Path(ctx.final_video_path)
        file_size = video_path_obj.stat().st_size
        
        result = VideoGenerationResult(
            video_path=ctx.final_video_path,
            storyboard=ctx.storyboard,
            duration=ctx.storyboard.total_duration,
            file_size=file_size
        )
        
        ctx.result = result
        
        logger.info(f"✅ Generated video: {ctx.final_video_path}")
        logger.info(f"   Duration: {ctx.storyboard.total_duration:.2f}s")
        logger.info(f"   Size: {file_size / (1024*1024):.2f} MB")
        logger.info(f"   Frames: {len(ctx.storyboard.frames)}")
        
        # Persist metadata
        await self._persist_task_data(ctx)
        
        return result

    def _public_input_params(self, ctx: PipelineContext) -> dict[str, Any]:
        input_params = ctx.params.copy()
        input_params.pop("progress_callback", None)
        input_params.pop("resume", None)
        input_params.pop("resume_task_id", None)
        input_params.pop("asset_reuse", None)
        input_params.pop("asset_reuse_fallback_reason", None)
        input_params["text"] = ctx.input_text
        if ctx.storyboard and not input_params.get("title"):
            input_params["title"] = ctx.storyboard.title
        elif ctx.title and not input_params.get("title"):
            input_params["title"] = ctx.title
        return input_params

    def _task_metadata(
        self,
        ctx: PipelineContext,
        status: str,
        error: str | None = None,
    ) -> dict[str, Any]:
        storyboard = ctx.storyboard
        task_id = (
            ctx.task_id
            or (storyboard.config.task_id if storyboard else None)
            or ctx.params.get("task_id")
        )
        created_at = (
            storyboard.created_at.isoformat()
            if storyboard and storyboard.created_at
            else datetime.now().isoformat()
        )
        completed_at = datetime.now().isoformat() if status in {"completed", "failed", "cancelled"} else None
        metadata = {
            "task_id": task_id,
            "created_at": created_at,
            "completed_at": completed_at,
            "status": status,
            "input": self._public_input_params(ctx),
            "result": {
                "video_path": ctx.final_video_path if status == "completed" else None,
                "duration": storyboard.total_duration if storyboard else 0,
                "file_size": ctx.result.file_size if ctx.result else 0,
                "n_frames": len(storyboard.frames) if storyboard else 0,
            },
            "config": {
                "llm_model": self.core.config.get("llm", {}).get("model", "unknown"),
                "llm_base_url": self.core.config.get("llm", {}).get("base_url", "unknown"),
                "comfyui_url": self.core.config.get("comfyui", {}).get("comfyui_url", "unknown"),
                "runninghub_enabled": bool(self.core.config.get("comfyui", {}).get("runninghub_api_key")),
            },
        }
        if error:
            metadata["error"] = error
        if hasattr(ctx, "current_stage"):
            metadata["failed_stage" if status == "failed" else "current_stage"] = ctx.current_stage
        if hasattr(ctx, "current_frame_index"):
            metadata["failed_frame_index" if status == "failed" else "current_frame_index"] = ctx.current_frame_index
        return metadata

    async def _persist_running_task_data(self, ctx: PipelineContext):
        task_id = (
            ctx.task_id
            or (ctx.storyboard.config.task_id if ctx.storyboard else None)
            or ctx.params.get("task_id")
        )
        if not task_id:
            return
        try:
            metadata = self._task_metadata(ctx, "running")
            await self.core.persistence.save_task_metadata(task_id, metadata)
            if ctx.storyboard:
                await self.core.persistence.save_storyboard(task_id, ctx.storyboard)
        except Exception as e:
            logger.error(f"Failed to persist running task data: {e}")

    async def handle_exception(self, ctx: PipelineContext, error: Exception):
        logger.error(f"Pipeline execution failed: {error}")
        task_id = (
            ctx.task_id
            or (ctx.storyboard.config.task_id if ctx.storyboard else None)
            or ctx.params.get("task_id")
        )
        if not task_id:
            return
        try:
            if ctx.storyboard:
                await self.core.persistence.save_storyboard(task_id, ctx.storyboard)
            metadata = self._task_metadata(ctx, "failed", error=str(error))
            await self.core.persistence.save_task_metadata(task_id, metadata)
        except Exception as persistence_error:
            logger.error(f"Failed to persist failed task data: {persistence_error}")

    async def handle_cancellation(self, ctx: PipelineContext):
        """Persist cancellation as its own terminal state."""
        task_id = (
            ctx.task_id
            or (ctx.storyboard.config.task_id if ctx.storyboard else None)
            or ctx.params.get("task_id")
        )
        if not task_id:
            return
        try:
            if ctx.storyboard:
                await self.core.persistence.save_storyboard(task_id, ctx.storyboard)
            metadata = self._task_metadata(ctx, "cancelled")
            await self.core.persistence.save_task_metadata(task_id, metadata)
        except Exception as persistence_error:
            logger.error(f"Failed to persist cancelled task data: {persistence_error}")

    async def _persist_task_data(self, ctx: PipelineContext):
        """
        Persist task metadata and storyboard to filesystem
        """
        try:
            storyboard = ctx.storyboard
            result = ctx.result
            task_id = storyboard.config.task_id
            
            if not task_id:
                logger.warning("No task_id in storyboard, skipping persistence")
                return
            
            metadata = self._task_metadata(ctx, "completed")
            metadata["result"] = {
                "video_path": result.video_path,
                "duration": result.duration,
                "file_size": result.file_size,
                "n_frames": len(storyboard.frames),
            }
            
            # Save metadata
            await self.core.persistence.save_task_metadata(task_id, metadata)
            logger.info(f"💾 Saved task metadata: {task_id}")
            
            # Save storyboard
            await self.core.persistence.save_storyboard(task_id, storyboard)
            logger.info(f"💾 Saved storyboard: {task_id}")
            
        except Exception as e:
            logger.error(f"Failed to persist task data: {e}")
            # Don't raise - persistence failure shouldn't break video generation
