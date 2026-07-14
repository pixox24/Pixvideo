# Web UI Guide

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
