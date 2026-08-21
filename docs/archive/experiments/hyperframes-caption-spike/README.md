# HyperFrames Caption Spike

This isolated experiment validates a 9:16 advanced-caption workflow without changing the Pixvideo production subtitle pipeline.

## Scope

- `caption-plan.json` is the renderer-neutral caption contract that a future Python/React integration will generate and edit.
- `index.html` renders a full 9:16 MP4 with a standard caption rail and one promoted keyword.
- `compositions/caption-overlay.html` renders the same captions on a transparent canvas for a later FFmpeg composition step.
- The experiment intentionally does not use HyperFrames embedded captions. That workflow is for single-subject talking-head/digital-human video, not Pixvideo's multi-shot image-motion output.

## Reproduce

```bash
cd experiments/hyperframes-caption-spike

# Static checks: 0 lint errors/warnings, browser validation, composition inspection.
npm run check

# Standalone 1080x1920 H.264 MP4, 30 fps.
npx --yes hyperframes@0.7.48 render . \
  --output renders/caption-spike.mp4 \
  --fps 30 --quality draft --workers 1 --strict

# Compact transparent overlay.
npx --yes hyperframes@0.7.48 render . \
  --composition compositions/caption-overlay.html \
  --format webm --output renders/caption-overlay.webm \
  --fps 30 --quality draft --workers 1 --strict

# Portable RGBA fallback for FFmpeg environments where VP9 alpha decoding is unavailable.
npx --yes hyperframes@0.7.48 render . \
  --composition compositions/caption-overlay.html \
  --format png-sequence --output renders/caption-overlay-frames \
  --fps 30 --quality draft --workers 1 --strict
```

## FFmpeg Composition Contract

The WebM output carries VP9 alpha. FFmpeg's default native VP9 decoder may discard that alpha channel, so the overlay input must explicitly use `libvpx-vp9`:

```bash
ffmpeg -y \
  -i source-video.mp4 \
  -c:v libvpx-vp9 -i renders/caption-overlay.webm \
  -filter_complex "[0:v][1:v]overlay=0:0:format=auto[v]" \
  -map "[v]" -map 0:a? -c:v libx264 -crf 18 -pix_fmt yuv420p \
  -c:a aac -shortest output.mp4
```

For the PNG fallback, use the sequence as the second input and remove `-c:v libvpx-vp9`:

```bash
ffmpeg -y \
  -i source-video.mp4 \
  -framerate 30 -i renders/caption-overlay-frames/frame_%06d.png \
  -filter_complex "[0:v][1:v]overlay=0:0:format=auto[v]" \
  -map "[v]" -map 0:a? -c:v libx264 -crf 18 -pix_fmt yuv420p \
  -c:a aac -shortest output.mp4
```

## Verified Locally

- HyperFrames `0.7.48` lint: 0 errors, 0 warnings.
- HyperFrames validation: no browser console errors; 11 text elements pass WCAG AA.
- Standalone MP4: 1080x1920 H.264, 30 fps, 4.8 seconds.
- WebM and PNG overlays: the 1.5-second keyword frame preserved transparency and composited correctly over white and black backgrounds using FFmpeg.

Render outputs are intentionally ignored by Git. This directory is a technical spike, not a production dependency yet.
