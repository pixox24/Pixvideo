# Pixelle React + FastAPI Fusion Plan

Date: 2026-07-07

## Execution Status

Implemented in the first fusion batch:

- Added FastAPI configuration endpoints under `/api/config`.
- Added React-compatible workbench endpoints:
  - `GET/POST /api/presets`
  - `POST /api/test-connection`
  - `POST /api/generate-script`
- Added persisted history endpoints under `/api/history`.
- Extended `/api/video/generate/async` to accept the Quick Create parameter surface and update task progress from backend `ProgressEvent`.
- Replaced the React project's Express mock server with Vite proxying to FastAPI.
- Removed the unused Node mock server entrypoint and mock-only dependencies.
- Wired React settings save to backend `config.yaml`.
- Wired React task submission to `/api/video/generate/async` and polling to `/api/tasks/{task_id}`.
- Wired React history loading/deletion/resume to `/api/history`.

Implemented in the second fusion batch:

- Loaded Quick Create resources from FastAPI:
  - `GET /api/resources/workflows/media`
  - `GET /api/resources/templates`
  - `GET /api/resources/bgm`
- Replaced static React workflow/template/BGM lists with backend resources.
- Removed unused mock workflow, BGM, template, and fixture history data from `src/data.ts`.
- Updated Quick Create generation requests to submit real `media_workflow`, `frame_template`, composition mode, motion/subtitle flags, MiniMax model, and emotion fields.
- Updated preset save/apply compatibility to include template, composition mode, motion/subtitle flags, MiniMax model, and emotion.
- Removed the old external mock TTS preview sound; the button now avoids playing fake audio until a real TTS preview endpoint is wired.

Still planned for a later batch:

- Add unified upload endpoints and wire custom media, digital human, image-to-video, and action-transfer upload flows.
- Serve the production React build from FastAPI as the single product entrypoint.
- Add streaming/SSE task progress when the task manager is ready for push updates.

## Objective

Replace the Streamlit-first product surface with the new React workbench while keeping the existing Python backend as the only source of business truth.

The final architecture must be:

```text
React/Vite workbench
  -> FastAPI REST/SSE API
  -> PixelleVideoCore
  -> LLM / TTS / Media / Video / Persistence / History / Files
```

The React app must not depend on Streamlit, mock generation, or the current Node in-memory API for real product behavior.

## Current State

### Backend

The existing `Pix24Video` repository already has:

- `pixelle_video/`: real business core and pipelines.
- `api/`: FastAPI app with health, LLM, TTS, image, content, video, task, file, resource, and frame routers.
- `web/`: legacy Streamlit UI.
- `config_manager`: persistent configuration and quick-create defaults.
- `HistoryManager` and `PersistenceService`: persisted generated task history under `output/`.

The API is useful but not yet complete for the new frontend. Main gaps:

- `VideoGenerateRequest` does not fully match the Streamlit quick-create parameter surface.
- Async generation does not stream detailed `ProgressEvent` updates yet.
- Persisted history endpoints are separate from the in-memory API task manager and are not exposed as a clean React-friendly API.
- Config read/save and quick-create preset endpoints are missing.
- Upload endpoints for images, videos, and reference audio are missing or not unified.
- Specialized pipelines shown in React, such as I2V, digital human, and action transfer, need API endpoints or an explicit "not yet wired" state.

### New Frontend

The sibling `Pixelle front` project is a React/Vite app with:

- `src/App.tsx`: workbench shell and tab routing.
- `QuickCreate`, `CustomMedia`, `DigitalHuman`, `ImageToVideo`, `ActionTransfer`, `HistoryList`, `SystemSettingsTab`, and `ConsolePanel`.
- `server.ts`: Express + Vite dev server with mock `/api/presets`, `/api/test-connection`, and `/api/generate-script`.
- `src/data.ts`: static voices, workflows, BGM, templates, and task fixtures.
- `startSimulation`: fake generation progress and fake completed video.

The UI is the right destination, but its data layer must be replaced.

## Non-Goals

- Do not rewrite `pixelle_video/`.
- Do not make React call Streamlit.
- Do not keep Express mock endpoints as production behavior.
- Do not remove `web/` until the React workbench covers the main workflows.
- Do not move secrets into the frontend.

## Target Development Topology

Development:

```text
FastAPI: http://127.0.0.1:8000
React:   http://127.0.0.1:5173
React Vite proxy -> FastAPI /api, /health, /docs, /openapi.json
```

Production/package:

```text
One FastAPI process:
  /api/*        backend API
  /files/*      generated files and assets
  /             React build
```

This keeps the user-facing product to a single address while keeping frontend development fast.

## API Contract To Add Or Fix

### Configuration

Add router: `api/routers/configuration.py`

Endpoints:

- `GET /api/config`
  - Returns sanitized config, validation status, quick-create defaults, and service readiness.
  - Never returns secret values in full; use booleans or masked strings.

- `PUT /api/config`
  - Saves LLM, ComfyUI, RunningHub, BizyAir, and MiniMax settings.
  - Reuses `config_manager.set_llm_config`, `set_comfyui_config`, and `save`.

- `POST /api/config/test`
  - Tests one service: `llm`, `comfyui`, `runninghub`, `bizyair`, or `minimax`.
  - Uses real backend checks where available.

- `GET /api/presets`
  - Returns saved quick-create production defaults.

- `POST /api/presets`
  - Saves reusable quick-create production defaults.
  - Must not save one-off content, title, uploaded files, generated task output, or temporary preview text.

### Resources

Existing `api/routers/resources.py` is mostly correct. Frontend should use:

- `GET /api/resources/workflows/tts`
- `GET /api/resources/workflows/media`
- `GET /api/resources/templates`
- `GET /api/resources/bgm`

Add later if needed:

- `GET /api/resources/voices`
- `GET /api/resources/templates/{template_key}/params`
- `GET /api/resources/templates/{template_key}/preview`

### Uploads

Add router: `api/routers/uploads.py`

Endpoints:

- `POST /api/uploads`
  - Accepts image, video, or audio.
  - Stores files under `data/uploads/{kind}/`.
  - Returns stable relative path and preview URL.

Allowed kinds:

- `image`
- `video`
- `audio`
- `digital_human`
- `action_reference`

### Video Generation

Extend `api/schemas/video.py` so React can submit the same parameters Streamlit can generate:

- `pipeline`
- `split_mode`
- `tts_inference_mode`
- `tts_voice`
- `tts_speed`
- `tts_workflow`
- `ref_audio`
- `minimax_model`
- `minimax_emotion`
- `frame_template`
- `template_type`
- `template_media_type`
- `template_params`
- `media_workflow`
- `prompt_prefix`
- `composition_mode`
- `image_motion_enabled`
- `subtitle_enabled`
- `image_motion_mode`
- `image_motion_strength`
- `image_fit_mode`
- `bgm_path`
- `bgm_volume`
- `media_width`
- `media_height`

Fix async generation:

- Attach `progress_callback`.
- Translate `ProgressEvent.progress` into task manager progress.
- Store status message, current frame, current step, and final video URL.

Main endpoint:

- `POST /api/video/generate/async`

Frontend should prefer async. Synchronous generation can stay for API consumers.

### Batch Generation

Add endpoint:

- `POST /api/video/generate/batch`

Inputs:

- `topics`
- shared quick-create config

Implementation can reuse `web.utils.batch_manager.SimpleBatchManager` only if it is UI-independent. If not, extract shared logic into an API-safe service later.

### Persisted History

Add router: `api/routers/history.py`

Endpoints:

- `GET /api/history`
  - Paginated persisted task list from `pixelle_video.history.get_task_list`.

- `GET /api/history/{task_id}`
  - Full metadata and storyboard.

- `DELETE /api/history/{task_id}`
  - Delete persisted task.

- `POST /api/history/{task_id}/resume`
  - Resume failed or interrupted persisted standard task.

This is separate from `/api/tasks`, which tracks current in-memory jobs.

### Files

Keep existing:

- `GET /api/files/{file_path:path}`

Frontend should use returned file URLs from API responses and not construct local filesystem paths.

## Frontend Changes

### Remove Real Dependency On `server.ts`

`server.ts` should not own product API behavior.

Options:

1. Replace `server.ts` with Vite dev server only and configure Vite proxy.
2. Keep Express only for serving built React assets, proxying `/api/*` to FastAPI in development.

Recommended first step: Vite proxy in `vite.config.ts`.

### Add API Client Layer

Create:

- `src/lib/api.ts`
- `src/lib/types.ts` or generated OpenAPI types later.

Client functions:

- `getConfig`
- `saveConfig`
- `testServiceConnection`
- `listPresets`
- `savePreset`
- `listResources`
- `generateVideoAsync`
- `getTask`
- `listTasks`
- `listHistory`
- `getHistoryDetail`
- `deleteHistoryTask`
- `resumeHistoryTask`
- `uploadAsset`

### Replace Mock State

Remove or stop using:

- `INITIAL_TASKS` for real history.
- `startSimulation`.
- Node `/api/generate-script`.
- Node `/api/presets`.
- local fake completed `videoUrl`.

React should:

- Submit generation to `POST /api/video/generate/async`.
- Poll `GET /api/tasks/{task_id}` until terminal status.
- Refresh persisted history after completion.
- Display real `video_url` from API result.
- Load resources from `/api/resources/*`.
- Load settings from `/api/config`.

### Preserve Draft UX

React can keep unsaved form draft state in component state or local storage, but saved production defaults must come from backend `/api/presets`.

Do not save:

- title
- script text
- topic text
- uploaded files
- preview text
- generated output

Do save:

- TTS mode, voice, speed
- MiniMax model, emotion
- ComfyUI TTS workflow
- template type and template
- composition mode
- image motion/subtitle preferences
- media workflow
- prompt prefix
- BGM and volume

## Streamlit Decommission Plan

Do this after React main workflows pass smoke tests:

1. Stop default scripts from launching `web/app.py`.
2. Update docs to use FastAPI + React.
3. Update Docker to remove Streamlit service.
4. Keep `web/` for one release as fallback/debug.
5. Remove Streamlit dependencies only after packaging confirms React covers required flows.

## Implementation Phases

### Phase 1: Contract And Foundation

- Add this document.
- Add backend config and history routers.
- Extend video schema and async progress.
- Add frontend API client.
- Configure Vite proxy to FastAPI.
- Replace new frontend presets/config/resource loading with real API calls.

Acceptance:

- `GET /api/config` works.
- `GET /api/history` works.
- `GET /api/resources/*` works.
- React loads resources from FastAPI.
- Frontend no longer requires `server.ts` mock endpoints for presets or settings.

### Phase 2: Quick Create End-To-End

- Map QuickCreate form to `VideoGenerateRequest`.
- Submit async generation to FastAPI.
- Poll task progress.
- Show real progress/status in `ConsolePanel`.
- Show real generated video URL.
- Save reusable quick-create config via backend.

Acceptance:

- User can create one quick-create task from React.
- No simulated task progress remains in the quick-create path.
- Result video comes from backend `/api/files`.

### Phase 3: History

- Replace `INITIAL_TASKS` with persisted history API.
- Add detail view mapping to metadata/storyboard.
- Wire delete/resume/download to backend.

Acceptance:

- History survives frontend refresh.
- Completed videos download from backend file endpoint.
- Failed/interrupted standard tasks can resume where backend supports it.

### Phase 4: Specialized Pipelines

- Wire Custom Media, Digital Human, I2V, and Action Transfer.
- If backend lacks a pipeline endpoint, expose a disabled/coming-soon state instead of fake generation.
- Add upload support for required files.

Acceptance:

- No tab shows fake final output.
- Unsupported flows clearly say what backend endpoint is missing.

### Phase 5: Old Frontend Cleanup

- Update scripts, Docker, docs, and packaging.
- Make React the default UI.
- Keep `web/` only as an explicit fallback for one release.

Acceptance:

- Default launch opens React workbench.
- Streamlit is not started by default.
- No user-facing copy references old Streamlit pages.

## Verification

Backend:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m py_compile api\app.py api\routers\*.py api\schemas\*.py
```

Frontend:

```powershell
npm.cmd run lint
npm.cmd run build
```

Smoke:

- Start FastAPI on `127.0.0.1:8000`.
- Start React on `127.0.0.1:5173`.
- Open React workbench.
- Confirm config, resources, and history load from FastAPI.
- Submit a quick-create task only when real service credentials are configured.

## Risks And Mitigations

- Risk: API schema drift between React and Python.
  - Mitigation: use OpenAPI-generated TypeScript client after Phase 1.

- Risk: Full generation is slow and hard to test on every change.
  - Mitigation: test API request mapping and task polling separately; reserve full generation for smoke tests.

- Risk: Removing Streamlit too early breaks fallback.
  - Mitigation: decommission in Phase 5 only.

- Risk: Node mock endpoints hide integration bugs.
  - Mitigation: remove or proxy them early.

## Immediate Execution Batch

The first implementation batch is:

1. Add backend configuration API.
2. Add backend persisted history API.
3. Extend video request schema and async progress mapping for quick-create parity.
4. Add React API client and Vite proxy.
5. Replace React preset/config/history/resource loading with real FastAPI calls while keeping UI behavior intact.
