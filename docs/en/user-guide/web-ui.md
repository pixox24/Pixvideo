# Web UI Guide

## Editing Workbench

### Project Generation Run

The workbench has one project-level **Start generation** action. It scans all scenes in timeline order and skips assets whose fingerprints and files are still valid. Each missing or stale scene runs TTS first, writes the measured audio duration back to the timeline, and then generates the image.

The run panel shows the current scene, phase, aggregate progress, and terminal counts. **Pause** and **Cancel** are cooperative signals: an in-flight provider request is allowed to return before the next scene is scheduled. A failed scene is recorded and later scenes continue. For a run with failures, **Retry failed only** creates a new run from the current project settings.

When a scene already has a current image, a regenerated image is stored as a candidate version. It does not replace the current preview or export snapshot until the user explicitly selects it. The active scene is locked while it is being generated; waiting scenes remain editable.

Queued, running, and paused runs are persisted in the project database. If the API restarts, the run is restored and resumes from its last unfinished phase. The browser polls the run once per second while it is active and stops polling at a terminal state.

After confirming 1-100 scenes in Quick Create, the default action creates a project and opens the workbench. Direct generation remains available when refinement is unnecessary. The left pane contains scenes and project assets, the center previews the selected image, the right inspector edits narration, prompts, and candidates, and the bottom timeline controls order and extra visual hold.

Image regeneration adds a candidate and never replaces the current version until **Use this version** is selected. Uploads remain local to the project. Saving narration does not automatically start TTS; voice regeneration is explicit. Batch operations are limited to prompt prefixes and image generation.

Export preflight requires a selected image and audio for each scene and freezes an immutable revision. Incomplete export requires a second confirmation. Completed or failed history items can be opened as projects without modifying the original history.

Detailed introduction to the Pixelle-Video Web interface features.

---

## Interface Layout

On desktop, the interface contains navigation, the creation workspace, and a collapsible task panel. On narrow screens, navigation and tasks become drawers so the workspace keeps the full viewport width. Service badges reflect backend configuration and detection; “not checked” is not presented as ready.

Quick Create is organized into five stages: Content, Storyboard, Voice & Visuals, Review & Generate, and Progress & Results. The current browser automatically saves an editable draft and restores it after a refresh.

---

## System Configuration

First-time use requires configuring LLM and image generation services. See [Configuration Guide](../getting-started/configuration.md).

---

## Content Input

### Generation Mode

- **AI Generate Content**: Enter a topic, AI creates script automatically
- **Manual Storyboard**: Edit narration and visual prompt for every scene
- **Batch Generation**: Enter one topic per line; every topic creates an independent video task

### Fixed Script Split Mode

When using fixed script mode, you can choose how to split the content:

- **By Paragraph**: Split by empty lines, each paragraph becomes a scene
- **By Line**: Split by line breaks, each line becomes a scene
- **By Sentence**: Smart sentence boundary detection, each sentence becomes a scene

### Background Music

- Built-in music supported
- Custom music files supported

---

## Voice Settings

### TTS Workflow

- Select TTS workflow
- Supports Edge-TTS, Index-TTS, etc.

### Reference Audio

- Upload reference audio for voice cloning
- Supports MP3/WAV/FLAC formats

---

## Visual Settings

### Image/Video Generation

- Select media generation workflow (image or video)
- Adjust prompt prefix to control style

### Video Template

- **Template Preview Gallery**: Visually preview all available templates
- Supports portrait (1080x1920) / landscape (1920x1080) / square (1080x1080)
- Template types:
  - `static_*.html`: Static templates (no AI-generated media)
  - `image_*.html`: Image templates (requires AI-generated images)
  - `video_*.html`: Video templates (requires AI-generated videos)

---

## Generate Video

Before submission, review the video count, scene count, voice, workflow, canvas, subtitles, BGM, and estimated narration duration. The action locks while submitting and uses an idempotency key to prevent duplicate jobs.

After clicking "Generate Video", the system will:

1. Generate video script
2. Generate images/videos for each scene
3. Synthesize voice narration
4. Compose final video

Automatically previews when complete.

Running jobs can be cancelled from the task panel. Cancelled, failed, and completed are distinct terminal states and stay consistent with History. Batch jobs can be cancelled or retried individually.

!!! note "Preview assets"
    TTS previews, “synthesize current copy,” and test images are configuration previews only. They are not reused by the final render, which produces assets from the reviewed settings.

---

## FAQ

The sidebar includes built-in FAQ for quick reference:

- Common configuration issues
- Generation failure solutions
- Performance optimization tips
