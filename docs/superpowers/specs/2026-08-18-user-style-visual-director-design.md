# User-Controlled Visual Style Director

## Goal

Improve narration-to-image prompt alignment while keeping visual style under the user's control through the existing frontend `promptPrefix` field.

## Design

- The image prompt system message is style-neutral. It owns semantic translation, keyword-to-visual-metaphor conversion, composition, lighting, sequence continuity, and negative constraints.
- Each narration yields one dominant visual claim. Abstract keywords become visible motifs; concrete facts such as dates, times, numbers, places, names, quotes, and processes receive visible evidence anchors.
- Text is conditional rather than globally forbidden. Calendars, clocks, tickets, maps, labels, charts, books, forms, and interfaces may carry short exact text when it is semantically necessary. Long or exact copy gets a clean carrier and reserved space for deterministic post-production overlay.
- When a narration establishes a clear protagonist, identity, wardrobe color blocks, and key props remain consistent. Otherwise, objects, spaces, shadows, or groups may carry the scene.
- Adjacent shots rotate scale and composition; every prompt names a motivated light source, shadow behavior, environment, emotion, and medium only when supplied by the user style prefix.
- A non-empty `promptPrefix` is bound as a whole-sequence style lock and remains separate from narration content. An empty prefix adds no implicit medium, palette, era, or camera look.
- Output remains the existing strict `{"image_prompts": ["..."]}` contract.

## Storyboard analysis and visual anchors

- The default `auto` splitter first uses sentence boundaries, then explicit pause punctuation for long sentences; it never character-slices and preserves the source narration.
- The backend exposes `POST /api/storyboard/analyze` for an on-demand semantic pass. It returns source-preserving units, estimated duration, boundary reason, rhythm/semantic counts, and warnings. LLM segmentation is attempted only for overlong units and is accepted only when concatenating returned text reconstructs the source exactly.
- When validated semantic segmentation supplies `visual_focus`, that hint is passed alongside the corresponding narration to image-prompt generation. It is a directional cue for the dominant visual claim, never TTS text or text to render in the image.
- Project creation applies the same narrow fallback for a single overlong auto-mode scene without a manual visual prompt. Hand-authored visual prompts preserve their scene boundaries.

## Frontend behavior

The Quick Create `promptPrefix` default becomes empty. Its placeholder gives an example without imposing a default style. Saved presets, drafts, test-image generation, and provider-bound prompt composition continue to use the field as before.

## Verification

Update prompt tests to assert the new semantic rules and verify that empty and non-empty style prefixes produce the expected system messages. Run the focused Python tests and the frontend TypeScript build.
