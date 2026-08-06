# AI 剪辑工作台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Every step below uses checkbox syntax and must be completed in order within its milestone.

**Goal:** 在现有 React 19 + FastAPI + `TaskManager` + `StandardPipeline` 基础上，把快捷创作扩展为“生成初稿 -> 三栏 AI 分镜精修 -> 版本确认 -> 导出”的本地项目工作台，支持 30–100 个分镜、单镜图片/TTS 重生成、项目内上传、轻量批量图片生成和可恢复导出。

**Architecture:** 保留现有快捷创作的直接成片路径和历史任务结构，新增项目域作为长期编辑状态的唯一来源。项目结构化数据使用标准库 `sqlite3` 保存，媒体使用项目目录保存；每个分镜的 TTS、图片候选和导出都登记为持久化生成记录，并通过现有 `TaskManager` 执行异步工作。标准流水线只增加“使用项目当前素材快照”的输入能力，不复制实现 TTS、媒体、字幕和 FFmpeg 合成。

**Tech Stack:** Python 3.11 `dataclasses`/`sqlite3`/FastAPI/Pydantic/pytest；React 19/TypeScript/Tailwind CSS/lucide-react；Node `node:test`；Playwright 浏览器 smoke；FFmpeg 和现有 Pixelle 媒体/TTS 服务。

**Design source:** `docs/superpowers/specs/2026-08-06-ai-editing-workbench-design.md`

**Execution rules:** 工作区当前存在用户未提交改动，执行者不得使用 `git reset --hard`、`git checkout --` 或删除无关文件。每个任务结束后只提交该任务列出的文件。真实 LLM、TTS、图片和视频服务不用于单元测试；所有生成测试使用 fake core/service 和临时目录。

---

## 交付顺序与里程碑

这不是一次性重写。每个里程碑都能独立验收：

1. **M0 基线与项目存储**：可以创建、读取、更新项目和版本，并在重启后恢复。
2. **M1 项目 API 与初稿任务**：快捷创作可以创建项目，分镜任务可渐进填充。
3. **M2 精修 API**：单镜提示词、旁白、上传、候选确认、顺序和时长可持久化。
4. **M3 工作台 UI**：桌面三栏工作台可浏览长列表、编辑单镜并显示任务状态。
5. **M4 批量与导出**：批量图片生成、导出检查、不可变快照和现有合成链路接通。
6. **M5 历史迁移、响应式和全量回归**：旧历史可打开为项目，直接成片旁路不回归，浏览器和文档完成。

若执行时需要把一个里程碑拆成独立分支，按上面的边界拆分，不改变接口命名和数据模型。

## 文件地图

### 新增后端文件

- `pixelle_video/models/workbench.py`：项目域的 Python 数据结构和枚举，不负责 IO。
- `pixelle_video/services/workbench_repository.py`：SQLite schema、迁移、事务、读写项目/分镜/版本/任务/导出记录。
- `pixelle_video/services/workbench_media.py`：项目媒体目录、路径安全、上传复制、生成结果下载和缩略图。
- `pixelle_video/services/workbench_jobs.py`：将 TTS/图片/导出工作封装成可被 `TaskManager` 执行的协程。
- `api/schemas/workbench.py`：项目域 API 请求和响应模型，所有外部字段使用 camelCase 别名。
- `api/routers/projects.py`：`/api/projects` 路由；不修改现有 preset 路由的职责。

### 修改后端文件

- `pixelle_video/service.py`：初始化并暴露 `workbench_repository`、`workbench_media`、`workbench_jobs`。
- `api/dependencies.py`：为项目路由提供已初始化的 core/repository 依赖。
- `api/app.py`：注册 `projects_router`。
- `api/tasks/models.py`：增加项目场景、图片候选、TTS 和导出任务类型。
- `api/tasks/manager.py`：保留内存执行，但允许项目任务使用稳定 request key，任务终态由项目仓库同步持久化。
- `api/schemas/video.py`：显式分镜上限从 30 扩展到 100；不向公共请求暴露任意本地路径。
- `api/routers/video.py`：保留现有直生成接口，抽取可复用的参数构造和 URL 转换逻辑。
- `api/routers/history.py`：历史详情增加“继续精修”入口需要的项目化信息。
- `pixelle_video/services/frame_processor.py`：改为复用 `WorkbenchMediaStore` 的下载/文件校验辅助，不改变现有帧处理行为。
- `pixelle_video/pipelines/standard.py`：支持内部 `existing_scene_assets` 快照，跳过已经存在的音频/图片生成，仅执行合成和拼接。
- `pixelle_video/config/schema.py`、`config.example.yaml`：记录可选项目存储目录和场景并发上限；缺省使用 `data/workbench` 和 3。

### 新增前端文件

- `frontend/src/lib/workbenchApi.ts`：项目 API 请求、上传、任务轮询和错误格式化。
- `frontend/src/lib/workbenchState.ts`：纯函数形式的版本确认、顺序重排、时长约束和批量输入构造。
- `frontend/src/components/ProjectWorkbench.tsx`：三栏布局和项目级状态编排。
- `frontend/src/components/SceneList.tsx`：分镜/素材标签、虚拟化滚动、多选和技术状态。
- `frontend/src/components/SceneInspector.tsx`：旁白、提示词、候选版本、上传和重生成。
- `frontend/src/components/WorkbenchTimeline.tsx`：单轨顺序、播放头和音频驱动时长编辑。
- `frontend/src/components/GenerationQueue.tsx`：项目分镜任务汇总、单项取消和重试。
- `frontend/src/components/ExportDialog.tsx`：导出检查、未完成项定位和二次确认。
- `frontend/src/lib/workbenchState.test.ts`：不依赖 DOM 的状态规则测试。

### 修改前端文件

- `frontend/src/types.ts`：增加 `Project`, `WorkbenchScene`, `AssetVersion`, `GenerationJob`, `ExportRevision` 和新的 `ActiveTab`。
- `frontend/src/lib/api.ts`：保留直生成 `submitVideoTask`，补充 quick-create 的项目提交结果映射。
- `frontend/src/components/QuickCreate.tsx`：默认 CTA 改为创建项目并进入工作台；保留直接成片次要按钮；场景输入上限扩展到 100。
- `frontend/src/App.tsx`：维护 `activeProjectId`，注册工作台视图，统一项目任务轮询和 Toast。
- `frontend/src/components/HistoryList.tsx`：为历史任务增加“打开为项目/继续精修”操作。
- `frontend/src/index.css`：只补充工作台滚动、拖动、焦点和窄屏抽屉样式，遵循现有深色视觉系统。

### 测试和文档文件

- `tests/models/test_workbench.py`
- `tests/services/test_workbench_repository.py`
- `tests/services/test_workbench_media.py`
- `tests/services/test_workbench_jobs.py`
- `tests/api/test_projects.py`
- `tests/api/test_project_scene_mutations.py`
- `tests/api/test_project_export.py`
- `tests/api/test_video_scenes.py`（扩展 100 分镜边界）
- `tests/api/test_history_summary.py`（历史项目入口）
- `tests/frontend/test_workbench_contract.py`
- `frontend/src/lib/workbenchState.test.ts`
- `frontend/src/lib/workbenchApi.test.ts`
- `tests/browser/project_workbench_smoke.py`
- `README.md`、`README_EN.md`、`docs/zh/user-guide/web-ui.md`、`docs/en/user-guide/web-ui.md`

---

## M0：项目域基础和本地存储

### Task 1: 定义项目域模型和 SQLite schema

**Files:**
- Create: `pixelle_video/models/workbench.py`
- Create: `tests/models/test_workbench.py`

- [ ] **Step 1: 写失败的模型测试**

测试必须锁定以下行为和字段命名，避免后续 API 与仓库漂移：

```python
from pixelle_video.models.workbench import (
    AssetSource,
    AssetVersion,
    GenerationKind,
    GenerationStatus,
    Project,
    Scene,
)


def test_scene_defaults_to_audio_driven_duration_and_no_current_asset():
    scene = Scene(project_id="p1", position=0, narration="旁白", visual_prompt="画面")

    assert scene.current_version_id is None
    assert scene.duration_mode == "audio"
    assert scene.manual_hold_seconds == 0
    assert scene.status == "pending"


def test_asset_version_keeps_prompt_snapshot_and_source():
    asset = AssetVersion(
        project_id="p1",
        scene_id="s1",
        source=AssetSource.AI,
        relative_path="assets/scenes/s1/versions/v1.png",
        prompt_snapshot="warm cinematic street",
    )

    assert asset.source.value == "ai"
    assert asset.prompt_snapshot == "warm cinematic street"


def test_generation_kind_values_are_stable_for_task_metadata():
    assert {item.value for item in GenerationKind} == {"scene", "image", "tts", "export"}
```

- [ ] **Step 2: 运行测试确认失败**

运行：`uv run --extra dev pytest tests/models/test_workbench.py -q`

预期：FAIL，提示 `pixelle_video.models.workbench` 尚不存在。

- [ ] **Step 3: 实现纯模型**

在 `workbench.py` 中使用 `dataclass` 和 `Enum`，统一使用 snake_case：

```python
class AssetSource(str, Enum):
    AI = "ai"
    UPLOAD = "upload"


class GenerationKind(str, Enum):
    SCENE = "scene"
    IMAGE = "image"
    TTS = "tts"
    EXPORT = "export"


class GenerationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Scene:
    project_id: str
    position: int
    narration: str
    visual_prompt: str
    scene_id: str = field(default_factory=lambda: uuid4().hex)
    current_version_id: str | None = None
    audio_relative_path: str | None = None
    subtitle_alignment: list[dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0
    manual_hold_seconds: float = 0.0
    duration_mode: str = "audio"
    status: str = "pending"
    updated_at: datetime = field(default_factory=datetime.now)
```

同文件增加 `Project`, `AssetVersion`, `GenerationJob`, `ExportRevision`，每个 ID 使用 `uuid4().hex`，时间使用 UTC aware datetime。`AssetVersion` 必须含 `project_id`, `scene_id | None`, `source`, `relative_path`, `thumbnail_relative_path | None`, `prompt_snapshot | None`, `parameters_json`, `created_at`。`ExportRevision` 保存导出时的 scene/asset/audio 快照 JSON，而不是指向可变的当前状态。

- [ ] **Step 4: 增加 SQLite schema 测试**

将 repository 的 schema 定义测试放在 `tests/services/test_workbench_repository.py`，先写：

```python
def test_schema_creates_all_project_tables(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")

    assert repository.table_names() == {
        "projects", "scenes", "asset_versions", "generation_jobs", "export_revisions"
    }
```

- [ ] **Step 5: 实现 repository 初始化和迁移**

创建 `pixelle_video/services/workbench_repository.py`。使用标准库 `sqlite3`，连接设置 `PRAGMA foreign_keys=ON`、`PRAGMA journal_mode=WAL`，迁移表结构如下：

```sql
CREATE TABLE IF NOT EXISTS projects (
  project_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  source TEXT NOT NULL,
  source_history_task_id TEXT UNIQUE,
  config_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scenes (
  scene_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  narration TEXT NOT NULL,
  visual_prompt TEXT NOT NULL DEFAULT '',
  current_version_id TEXT,
  audio_relative_path TEXT,
  subtitle_alignment_json TEXT NOT NULL DEFAULT '[]',
  duration_seconds REAL NOT NULL DEFAULT 0,
  manual_hold_seconds REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  updated_at TEXT NOT NULL,
  UNIQUE(project_id, position)
);
CREATE TABLE IF NOT EXISTS asset_versions (
  version_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  scene_id TEXT REFERENCES scenes(scene_id) ON DELETE CASCADE,
  source TEXT NOT NULL,
  relative_path TEXT NOT NULL,
  thumbnail_relative_path TEXT,
  prompt_snapshot TEXT,
  parameters_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS generation_jobs (
  job_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  scene_id TEXT REFERENCES scenes(scene_id) ON DELETE SET NULL,
  kind TEXT NOT NULL,
  task_id TEXT NOT NULL UNIQUE,
  request_snapshot_json TEXT NOT NULL,
  status TEXT NOT NULL,
  progress REAL NOT NULL DEFAULT 0,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS export_revisions (
  export_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  snapshot_json TEXT NOT NULL,
  output_relative_path TEXT,
  status TEXT NOT NULL,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

`Project` 额外保存 `source_history_task_id: str | None`，迁移来源为空时为 NULL；repository 在 `projects.source_history_task_id` 上建立唯一约束。公共方法必须包含：`create_project`, `get_project`, `list_project_scenes`, `update_project`, `update_scene`, `reorder_scenes`, `create_asset_version`, `select_asset_version`, `create_generation_job`, `update_generation_job`, `create_export_revision`, `update_export_revision`。所有写操作使用单次事务；序列化通过 `json.dumps(..., ensure_ascii=False)`。

- [ ] **Step 6: 运行模型和仓库测试**

运行：`uv run --extra dev pytest tests/models/test_workbench.py tests/services/test_workbench_repository.py -q`

预期：所有测试 PASS，且临时 SQLite 关闭后重新打开仍能读到项目、scene 和 asset version。

- [ ] **Step 7: 提交里程碑**

```bash
git add pixelle_video/models/workbench.py pixelle_video/services/workbench_repository.py tests/models/test_workbench.py tests/services/test_workbench_repository.py
git commit -m "feat: add workbench project repository"
```

### Task 2: 项目媒体目录和公共下载/缩略图服务

**Files:**
- Create: `pixelle_video/services/workbench_media.py`
- Create: `tests/services/test_workbench_media.py`
- Modify: `pixelle_video/services/frame_processor.py`

- [ ] **Step 1: 写失败的路径和上传测试**

```python
def test_upload_is_copied_inside_project_root(tmp_path):
    source = tmp_path / "input.png"
    source.write_bytes(b"png-bytes")
    store = WorkbenchMediaStore(tmp_path / "projects")

    relative_path = store.copy_upload("p1", "s1", source, "my-image.png")

    assert relative_path == "assets/scenes/s1/uploads/my-image.png"
    assert (tmp_path / "projects" / "p1" / relative_path).read_bytes() == b"png-bytes"


def test_relative_path_cannot_escape_project_root(tmp_path):
    store = WorkbenchMediaStore(tmp_path / "projects")

    with pytest.raises(ValueError, match="outside project"):
        store.resolve("p1", "../../secret.txt")
```

- [ ] **Step 2: 运行测试确认失败**

运行：`uv run --extra dev pytest tests/services/test_workbench_media.py -q`

预期：FAIL，提示 `WorkbenchMediaStore` 尚不存在。

- [ ] **Step 3: 实现路径安全、复制和下载**

`WorkbenchMediaStore` 默认根目录为 `data/workbench/projects`，测试可以传入临时根目录。所有数据库只存相对路径；`resolve(project_id, relative_path)` 必须使用 `Path.resolve()` 并验证结果位于项目根目录内。提供：

```python
class WorkbenchMediaStore:
    def project_root(self, project_id: str) -> Path: ...
    def resolve(self, project_id: str, relative_path: str) -> Path: ...
    def copy_upload(self, project_id: str, scene_id: str, source: Path, filename: str) -> str: ...
    async def download_result(self, project_id: str, scene_id: str, source_url: str, version_id: str) -> str: ...
    def create_thumbnail(self, absolute_path: Path, relative_path: str) -> str: ...
    def to_api_url(self, project_id: str, relative_path: str, request: Request) -> str: ...
```

上传文件名用 `Path(filename).name` 清理，并通过扩展名和 Pillow 解码验证图片。下载只允许 `http`、`https` 或已经存在且位于项目根目录内的本地文件；使用 `httpx.AsyncClient` 读取到临时文件，校验大小和 Pillow 解码后再原子 `replace`。缩略图固定放在 `assets/thumbnails`，最长边 320 像素。

- [ ] **Step 4: 提取 FrameProcessor 的共享下载逻辑**

把 `pixelle_video/services/frame_processor.py` 中 `_download_media` 的 HTTP 下载和临时文件校验逻辑迁移到 `WorkbenchMediaStore.download_result` 的私有 helper，再让 `FrameProcessor` 调用公共 helper。保持原方法名兼容旧调用，新增测试断言现有 `FrameProcessor` 下载行为不变。

- [ ] **Step 5: 运行服务测试和媒体回归**

运行：`uv run --extra dev pytest tests/services/test_workbench_media.py tests/services/test_frame_processor_composition.py -q`

预期：PASS；路径逃逸、无效图片、下载失败都不留下最终版本文件。

- [ ] **Step 6: 提交里程碑**

```bash
git add pixelle_video/services/workbench_media.py pixelle_video/services/frame_processor.py tests/services/test_workbench_media.py
git commit -m "feat: add safe workbench media storage"
```

### Task 3: 将项目服务挂入 PixelleVideoCore 和任务类型

**Files:**
- Modify: `pixelle_video/service.py`
- Modify: `api/dependencies.py`
- Modify: `api/tasks/models.py`
- Modify: `api/tasks/__init__.py`
- Modify: `api/tasks/manager.py`
- Modify: `pixelle_video/config/schema.py`
- Modify: `config.example.yaml`
- Create: `tests/services/test_workbench_core_wiring.py`

- [ ] **Step 1: 写失败的初始化测试**

```python
@pytest.mark.asyncio
async def test_core_initializes_workbench_services(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXVIDEO_WORKBENCH_DIR", str(tmp_path))
    core = PixelleVideoCore()
    await core.initialize()

    assert core.workbench_repository is not None
    assert core.workbench_media is not None
    await core.cleanup()
```

- [ ] **Step 2: 实现 wiring 和任务类型**

在 `PixelleVideoCore.__init__` 声明 `workbench_repository` 和 `workbench_media` 两个属性，在 `initialize()` 中用 `get_data_path("workbench")` 或配置覆盖创建服务。`cleanup()` 不删除项目文件，只关闭 SQLite 连接。`WorkbenchJobService` 在 Task 5 创建完成后再挂入 `core.workbench_jobs`，不要在本任务引用尚未存在的 job service。`TaskType` 增加：

```python
class TaskType(str, Enum):
    VIDEO_GENERATION = "video_generation"
    WORKBENCH_SCENE = "workbench_scene"
    WORKBENCH_IMAGE = "workbench_image"
    WORKBENCH_TTS = "workbench_tts"
    WORKBENCH_EXPORT = "workbench_export"
```

`TaskManager.create_task()` 的 request key 继续复用已有幂等机制；不把项目任务写入内存以外的第二份任务列表，项目仓库的 `generation_jobs` 是持久化镜像。`TaskManager` 的 cleanup 不删除仓库记录。

- [ ] **Step 3: 运行服务初始化回归**

运行：`uv run --extra dev pytest tests/services/test_workbench_core_wiring.py tests/api/test_video_task_identity.py -q`

预期：PASS，现有任务 ID、取消和 core cleanup 测试不回归。

- [ ] **Step 4: 提交里程碑**

```bash
git add pixelle_video/service.py api/dependencies.py api/tasks/models.py api/tasks/__init__.py api/tasks/manager.py pixelle_video/config/schema.py config.example.yaml tests/services/test_workbench_core_wiring.py
git commit -m "feat: wire workbench services into core"
```

---

## M1：项目 API 和渐进初稿生成

### Task 4: 定义项目 API schema 和读取/创建路由

**Files:**
- Create: `api/schemas/workbench.py`
- Create: `api/routers/projects.py`
- Modify: `api/app.py`
- Create: `tests/api/test_projects.py`

- [ ] **Step 1: 写 API contract 测试**

测试使用直接调用路由函数和 fake repository，覆盖以下请求/响应：

```python
def test_create_project_accepts_100_explicit_scenes():
    request = CreateProjectRequest(
        title="长项目",
        scenes=[
            {"narration": f"旁白 {index}", "visualPrompt": f"画面 {index}"}
            for index in range(100)
        ],
        config={"mediaWidth": 1080, "mediaHeight": 1920},
    )

    assert len(request.scenes) == 100


def test_create_project_rejects_blank_scene_narration():
    with pytest.raises(ValidationError):
        CreateProjectRequest(title="x", scenes=[{"narration": "  "}])
```

- [ ] **Step 2: 实现 schema**

`api/schemas/workbench.py` 使用 Pydantic camelCase alias，固定以下结构：

```python
class CreateProjectScene(BaseModel):
    narration: str = Field(..., min_length=1)
    visual_prompt: str = Field("", alias="visualPrompt")


class CreateProjectRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    scenes: list[CreateProjectScene] = Field(..., min_length=1, max_length=100)
    config: dict[str, Any] = Field(default_factory=dict)
    source: Literal["quick-create", "history"] = "quick-create"


class AssetVersionResponse(BaseModel):
    version_id: str = Field(alias="versionId")
    source: Literal["ai", "upload"]
    image_url: str = Field(alias="imageUrl")
    thumbnail_url: str | None = Field(default=None, alias="thumbnailUrl")
    prompt_snapshot: str | None = Field(default=None, alias="promptSnapshot")
    created_at: str = Field(alias="createdAt")


class ProjectSceneResponse(BaseModel):
    scene_id: str = Field(alias="sceneId")
    position: int
    narration: str
    visual_prompt: str = Field(alias="visualPrompt")
    current_version_id: str | None = Field(alias="currentVersionId")
    audio_url: str | None = Field(alias="audioUrl")
    duration_seconds: float = Field(alias="durationSeconds")
    manual_hold_seconds: float = Field(alias="manualHoldSeconds")
    status: str
    versions: list[AssetVersionResponse]


class GenerationJobResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    task_id: str = Field(alias="taskId")
    scene_id: str | None = Field(default=None, alias="sceneId")
    kind: Literal["scene", "image", "tts", "export"]
    status: str
    progress: float
    error: str | None = None


class ProjectResponse(BaseModel):
    project_id: str = Field(alias="projectId")
    title: str
    source: str
    source_history_task_id: str | None = Field(default=None, alias="sourceHistoryTaskId")
    config: dict[str, Any]
    scenes: list[ProjectSceneResponse]
    jobs: list[GenerationJobResponse]
    updated_at: str = Field(alias="updatedAt")
```

响应必须携带 `projectId`, `title`, `config`, `scenes`, `jobs`, `updatedAt`。不要在响应中暴露任意绝对路径。

- [ ] **Step 3: 实现创建/读取项目路由**

在 `api/routers/projects.py` 使用 `APIRouter(prefix="/projects")`，实现：

```python
@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(body: CreateProjectRequest, core: PixelleVideoDep): ...


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, core: PixelleVideoDep, request: Request): ...
```

创建时在一个 repository 事务内写入 project 和 scene 草稿，响应先返回所有 scene 和空的 `pending` jobs；任务调度由 Task 5 在 job service 可用后接入，不在本任务提前引用未实现的服务。项目不存在返回 404，路径引用通过 `WorkbenchMediaStore.to_api_url` 转换。

- [ ] **Step 4: 注册 router 并运行 API 测试**

在 `api/app.py` import `projects_router` 并使用 `api_config.api_prefix` 注册。运行：

`uv run --extra dev pytest tests/api/test_projects.py -q`

预期：PASS；创建 100 个分镜返回 201、保存 100 个 scene，空旁白返回 422，未知项目返回 404。

- [ ] **Step 5: 提交里程碑**

```bash
git add api/schemas/workbench.py api/routers/projects.py api/app.py tests/api/test_projects.py
git commit -m "feat: add workbench project API"
```

### Task 5: 实现分镜初稿任务和独立任务状态

**Files:**
- Create: `pixelle_video/services/workbench_jobs.py`
- Modify: `api/routers/projects.py`
- Modify: `pixelle_video/service.py`
- Create: `tests/services/test_workbench_jobs.py`
- Create: `tests/api/test_project_jobs.py`

- [ ] **Step 1: 写 fake service 测试**

测试不得调用真实供应商，使用 fake core：

```python
@pytest.mark.asyncio
async def test_scene_job_creates_audio_and_first_image_as_current_version(tmp_path):
    core = FakeCore(
        tts_result="audio.mp3",
        media_result=MediaResult(media_type="image", url="https://cdn.test/image.png"),
    )
    service = WorkbenchJobService(core, repository, media_store)

    await service.run_scene_job(project_id="p1", scene_id="s1", task_id="t1")

    scene = repository.get_scene("s1")
    assert scene.current_version_id is not None
    assert scene.audio_relative_path.endswith(".mp3")
    assert scene.status == "completed"
```

- [ ] **Step 2: 实现 job service 方法**

提供明确方法签名：

```python
class WorkbenchJobService:
    async def run_scene_job(self, project_id: str, scene_id: str, task_id: str) -> None: ...
    async def run_image_job(self, project_id: str, scene_id: str, task_id: str, prompt_snapshot: str) -> None: ...
    async def run_tts_job(self, project_id: str, scene_id: str, task_id: str, narration_snapshot: str) -> None: ...
    async def run_export_job(self, project_id: str, export_id: str, task_id: str) -> None: ...
```

`run_scene_job` 顺序为 TTS -> 计算音频时长/对齐 -> 图片 -> 创建 thumbnail -> 写 AssetVersion；如果 scene 没有 `current_version_id`，第一次成功的图片才自动选中。`run_image_job` 对已有 current version 只追加候选，绝不覆盖；`run_tts_job` 只更新当前 scene 的 audio、alignment 和音频驱动时长。所有异常写入 `generation_jobs.error` 和 scene status，同时重新抛出给 `TaskManager`，确保任务终态为 failed。

使用现有 `core.tts(text=..., inference_mode=..., voice=..., speed=..., output_path=...)` 和 `core.media(prompt=..., media_type="image", workflow=..., width=..., height=...)`。媒体 URL 统一通过 `WorkbenchMediaStore.download_result` 本地化；MiniMax 对齐 sidecar 继续使用现有 `subtitle_alignment` 解析器。

- [ ] **Step 3: 接入 TaskManager**

在 `PixelleVideoCore.initialize()` 完成 `WorkbenchJobService` 构造并挂到 `core.workbench_jobs`，然后在创建项目、单镜重生成和 TTS 更新路由中统一使用：

```python
task = task_manager.create_task(
    TaskType.WORKBENCH_SCENE,
    request_params={"project_id": project_id, "scene_id": scene_id},
    request_key=f"workbench:{project_id}:scene:{scene_id}:draft:{revision}",
)
repository.create_generation_job(..., task_id=task.task_id, kind="scene")
await task_manager.execute_task(task.task_id, jobs.run_scene_job, project_id, scene_id, task.task_id)
```

任务协程开始/结束/失败时更新 repository；`TaskManager.update_progress` 用 0/25/60/100 和中文阶段消息更新全局任务面板。项目读取接口合并 SQLite job 和内存 task 状态，应用重启后 SQLite 状态仍可显示。

- [ ] **Step 4: 运行 job/API 测试**

运行：`uv run --extra dev pytest tests/services/test_workbench_jobs.py tests/api/test_project_jobs.py -q`

预期：PASS；候选生成不覆盖旧版本，TTS 失败不删除旧音频，单项失败不改变其他 scene 状态，取消任务保持 `cancelled`。

- [ ] **Step 5: 提交里程碑**

```bash
git add pixelle_video/services/workbench_jobs.py api/routers/projects.py pixelle_video/service.py tests/services/test_workbench_jobs.py tests/api/test_project_jobs.py
git commit -m "feat: add progressive workbench scene jobs"
```

---

## M2：分镜精修 API、上传、排序和时长

### Task 6: 实现单镜修改、候选确认和项目内上传

**Files:**
- Modify: `api/schemas/workbench.py`
- Modify: `api/routers/projects.py`
- Modify: `pixelle_video/services/workbench_jobs.py`
- Create: `tests/api/test_project_scene_mutations.py`

- [ ] **Step 1: 写失败的 mutation 测试**

```python
@pytest.mark.asyncio
async def test_selecting_candidate_updates_current_version_without_deleting_previous(...):
    response = await select_asset_version("p1", "s1", "v2", core=fake_core)

    assert response["currentVersionId"] == "v2"
    assert repository.get_asset("v1") is not None


@pytest.mark.asyncio
async def test_prompt_regeneration_uses_submitted_snapshot(...):
    response = await regenerate_image("p1", "s1", RegenerateImageRequest(prompt="new prompt"), ...)

    job = repository.get_generation_job(response["jobId"])
    assert json.loads(job.request_snapshot_json)["prompt"] == "new prompt"
```

- [ ] **Step 2: 增加请求模型和路由**

实现以下 endpoint 和输入约束：

```text
PATCH /api/projects/{project_id}/scenes/{scene_id}
  {"visualPrompt": "...", "narration": "..."}
POST /api/projects/{project_id}/scenes/{scene_id}/image-generations
  {"prompt": "..."}
POST /api/projects/{project_id}/scenes/{scene_id}/tts
  {"narration": "..."}
POST /api/projects/{project_id}/scenes/{scene_id}/uploads
  multipart file=image
POST /api/projects/{project_id}/scenes/{scene_id}/versions/{version_id}/select
POST /api/projects/{project_id}/scenes/reorder
  {"sceneIds": ["..."]}
```

PATCH 只保存文本草稿，不隐式创建生成任务。图片/TTS endpoint 复制请求快照并返回 `jobId`。版本确认验证 version 属于指定 project/scene，上传限制图片 MIME、项目路径和合理的文件大小，上传成功后返回候选 version。所有 endpoint 对未知 project/scene/version 返回 404，对越界时长返回 422。

- [ ] **Step 3: 实现音频驱动时长校验**

在 `workbench.py`/repository 中提供纯函数：

```python
def effective_scene_duration(audio_seconds: float, manual_hold_seconds: float) -> float:
    return max(float(audio_seconds), float(audio_seconds) + max(manual_hold_seconds, 0.0))
```

`manual_hold_seconds` 只能为非负数；排序更新一次事务内重写 0..N-1 position。不要允许 PATCH 将 duration 设为小于音频时长。

- [ ] **Step 4: 运行 mutation 测试**

运行：`uv run --extra dev pytest tests/api/test_project_scene_mutations.py tests/services/test_workbench_repository.py -q`

预期：PASS；旧版本保留、提示词快照稳定、旁白变更只创建 TTS job、顺序无重复 position、非法上传和非法时长被拒绝。

- [ ] **Step 5: 提交里程碑**

```bash
git add api/schemas/workbench.py api/routers/projects.py pixelle_video/services/workbench_jobs.py tests/api/test_project_scene_mutations.py
git commit -m "feat: add workbench scene editing and versions"
```

### Task 7: 扩展长项目边界并保留直生成兼容

**Files:**
- Modify: `api/schemas/video.py`
- Modify: `api/routers/workbench.py`
- Modify: `frontend/src/components/QuickCreate.tsx`
- Modify: `tests/api/test_video_scenes.py`
- Modify: `tests/api/test_workbench_generate_script.py`
- Modify: `tests/api/test_workbench_presets.py`
- Create: `tests/frontend/test_workbench_scene_limit.py`

- [ ] **Step 1: 写边界测试**

```python
def test_video_request_accepts_100_explicit_scenes(monkeypatch):
    monkeypatch.setattr("api.routers.video._resolve_media_size", lambda _: (1080, 1920))
    request = VideoGenerateRequest(
        text="long project",
        mode="fixed",
        scenes=[{"narration": f"scene {i}"} for i in range(100)],
    )
    assert len(request.scenes) == 100


def test_video_request_rejects_101_explicit_scenes():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(text="x", mode="fixed", scenes=[{"narration": str(i)} for i in range(101)])
```

- [ ] **Step 2: 修改公共上限**

把 `VideoGenerateRequest.scenes.max_length`、`n_scenes.le`、QuickCreate `input max`、`GenerateScriptRequest.sceneCount`、`GenerateCopyDraftRequest.sceneCount` 和 preset `sceneCount` 存储边界统一为 100；同步给 `tests/api/test_workbench_generate_script.py` 增加 100/101 边界。`targetCharCount` 仍保持 50–3000，按场景字数计算函数继续保证每段至少 5 个词，不能只改前端数字。

前端的 batch 模式仍表示“多个独立视频任务”，不把它误改成项目内场景批量；新的项目批量生成在 M4 单独实现。

- [ ] **Step 3: 运行边界和现有 preset 测试**

运行：`uv run --extra dev pytest tests/api/test_video_scenes.py tests/api/test_workbench_presets.py tests/frontend/test_workbench_scene_limit.py -q`

预期：100 通过、101 被 FastAPI/Pydantic 拒绝，旧 preset normalization 和直接成片 payload 继续通过。

- [ ] **Step 4: 提交里程碑**

```bash
git add api/schemas/video.py api/routers/workbench.py frontend/src/components/QuickCreate.tsx tests/api/test_video_scenes.py tests/api/test_workbench_presets.py tests/frontend/test_workbench_scene_limit.py
git commit -m "feat: support long workbench storyboards"
```

---

## M3：前端项目状态和三栏精修台

### Task 8: 增加 TypeScript 类型、API client 和纯状态规则

**Files:**
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/lib/workbenchApi.ts`
- Create: `frontend/src/lib/workbenchState.ts`
- Create: `frontend/src/lib/workbenchState.test.ts`
- Create: `frontend/src/lib/workbenchApi.test.ts`

- [ ] **Step 1: 写纯函数失败测试**

```ts
import { strict as assert } from "node:assert";
import test from "node:test";
import { reorderScenes, selectAssetVersion, clampManualHold } from "./workbenchState";

test("reorderScenes rewrites positions without mutating input", () => {
  const input = [{ sceneId: "a", position: 0 }, { sceneId: "b", position: 1 }];
  assert.deepEqual(reorderScenes(input, ["b", "a"]).map((scene) => scene.sceneId), ["b", "a"]);
  assert.equal(input[0].position, 0);
});

test("manual hold cannot reduce audio duration", () => {
  assert.equal(clampManualHold(4.2, -1), 0);
  assert.equal(clampManualHold(4.2, 2), 2);
});

test("selectAssetVersion updates only selected scene", () => {
  const next = selectAssetVersion(projectFixture, "s2", "v9");
  assert.equal(next.scenes.find((scene) => scene.sceneId === "s2")?.currentVersionId, "v9");
  assert.equal(next.scenes.find((scene) => scene.sceneId === "s1")?.currentVersionId, "v1");
});
```

- [ ] **Step 2: 实现类型和纯函数**

在 `types.ts` 增加以下稳定边界：

```ts
export type WorkbenchJobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";
export interface AssetVersion { versionId: string; source: "ai" | "upload"; imageUrl: string; thumbnailUrl?: string; promptSnapshot?: string; createdAt: string; }
export interface WorkbenchScene { sceneId: string; position: number; narration: string; visualPrompt: string; currentVersionId: string | null; audioUrl?: string; durationSeconds: number; manualHoldSeconds: number; status: string; versions: AssetVersion[]; }
export interface GenerationJob { jobId: string; taskId: string; sceneId?: string; kind: "scene" | "image" | "tts" | "export"; status: WorkbenchJobStatus; progress: number; error?: string; }
export interface Project { projectId: string; title: string; config: Record<string, unknown>; scenes: WorkbenchScene[]; jobs: GenerationJob[]; updatedAt: string; }
export interface QuickCreateInput { title: string; scenes: Array<{ id?: number; ttsText: string; visualPrompt: string }>; [key: string]: unknown; }
```

`workbenchApi.ts` 提供 `createProject`, `fetchProject`, `patchScene`, `regenerateImage`, `regenerateTts`, `uploadSceneAsset`, `selectAssetVersion`, `reorderScenes`, `submitBatchImageGeneration`, `createExport`, `cancelWorkbenchJob`。所有函数复用 `formatApiErrorValue`/`requestJson` 的错误格式化，不允许组件直接 `fetch`。

- [ ] **Step 3: 运行 Node 测试确认失败再通过**

运行：`cd frontend && npx tsx --test src/lib/workbenchState.test.ts src/lib/workbenchApi.test.ts`

预期第一轮因函数不存在 FAIL；实现后 PASS。再运行 `npm run lint`，预期 TypeScript 无错误。

- [ ] **Step 4: 提交类型/API 基础**

```bash
git add frontend/src/types.ts frontend/src/lib/workbenchApi.ts frontend/src/lib/workbenchState.ts frontend/src/lib/workbenchState.test.ts frontend/src/lib/workbenchApi.test.ts
git commit -m "feat: add workbench client contracts"
```

### Task 9: 接入 QuickCreate 和 App 项目导航

**Files:**
- Modify: `frontend/src/components/QuickCreate.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types.ts`
- Create: `tests/frontend/test_workbench_entry_flow.py`

- [ ] **Step 1: 写入口契约测试**

沿用现有源码契约测试风格，断言：

```python
def test_quick_create_has_project_entry_and_direct_export_path():
    source = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    assert "onCreateProject" in source
    assert "生成初稿并打开工作台" in source
    assert "直接生成成片" in source


def test_app_registers_project_workbench_tab():
    source = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    assert 'activeTab === "project-workbench"' in source
    assert "activeProjectId" in source
```

- [ ] **Step 2: 实现项目提交回调**

在 `App.tsx` 增加：

```tsx
const [activeProjectId, setActiveProjectId] = useState<string | null>(null);

const handleCreateProject = async (input: QuickCreateInput) => {
  const project = await createProject(input);
  setActiveProjectId(project.projectId);
  setActiveTab("project-workbench");
  return project.projectId;
};
```

`QuickCreate` 的主 CTA 调用 `onCreateProject`；当前 `onGenerateTask` 保留给“直接生成成片”。提交失败时不切换页面，显示现有 Toast。`activeTab` union 增加 `project-workbench`，顶部标题、移动导航和任务面板都要能识别该页面。

- [ ] **Step 3: 运行入口测试和现有 QuickCreate 回归**

运行：`uv run --extra dev pytest tests/frontend/test_workbench_entry_flow.py tests/frontend/test_quick_create_workflow.py tests/frontend/test_quick_create_submit_payload.py -q`

预期：源码契约和现有 quick-create 行为 PASS；直接成片仍提交 `/api/video/generate/async`，默认入口提交 `/api/projects`。

- [ ] **Step 4: 提交入口集成**

```bash
git add frontend/src/components/QuickCreate.tsx frontend/src/App.tsx frontend/src/lib/api.ts frontend/src/types.ts tests/frontend/test_workbench_entry_flow.py
git commit -m "feat: open workbench after quick create"
```

### Task 10: 实现三栏工作台骨架和长分镜列表

**Files:**
- Create: `frontend/src/components/ProjectWorkbench.tsx`
- Create: `frontend/src/components/SceneList.tsx`
- Create: `frontend/src/components/SceneInspector.tsx`
- Create: `frontend/src/components/GenerationQueue.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/index.css`
- Create: `tests/frontend/test_workbench_layout_contract.py`

- [ ] **Step 1: 写布局契约测试**

```python
def test_workbench_layout_has_scene_asset_preview_inspector_and_queue_regions():
    source = Path("frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
    for marker in ["分镜", "素材", "画面预览", "提示词", "重新生成", "GenerationQueue"]:
        assert marker in source
```

- [ ] **Step 2: 实现最小可渲染骨架**

`ProjectWorkbench` 只负责：加载 project、`selectedSceneId`、`selectedSceneIds`、refresh、错误 Toast 和子组件布局。布局使用 `grid-template-columns: minmax(190px, 240px) minmax(0, 1fr) minmax(280px, 360px)`，底部 timeline 留给 Task 11。

`SceneList` 使用固定行高（例如 72px）和 `overflow-y-auto`，先用窗口化切片函数 `visibleScenes = scenes.slice(start, end)`，不引入新的虚拟列表依赖。每行显示缩略图、编号、旁白前 42 个字符和 pending/running/completed/failed 技术状态；多选只在显式勾选时启用。

`SceneInspector` 在没有选中 scene 时显示空状态；选中后渲染旁白 textarea、提示词 textarea、当前图片和候选版本列表。所有按钮使用 `lucide-react` 图标，图标按钮提供 `title`/`aria-label`。

`GenerationQueue` 只读取 project.jobs，显示当前项目 job，提供单项取消/重试回调；不复用右侧全局 `ConsolePanel` 的布局样式。

- [ ] **Step 3: 接入 App 并处理加载/重载**

在 `App.tsx` 渲染：

```tsx
{activeTab === "project-workbench" && activeProjectId && (
  <ProjectWorkbench projectId={activeProjectId} addToast={addToast} />
)}
```

工作台加载失败保留重试按钮；页面切换时停止旧轮询；项目更新后只刷新当前 project，不覆盖 QuickCreate 草稿。

- [ ] **Step 4: 运行 lint 和布局契约**

运行：`uv run --extra dev pytest tests/frontend/test_workbench_layout_contract.py -q`；`cd frontend && npm run lint`。

预期：PASS，无 TypeScript 错误；列表包含 100 个 fixture scene 时滚动区域高度稳定，不出现页面横向溢出。

- [ ] **Step 5: 提交 UI 骨架**

```bash
git add frontend/src/components/ProjectWorkbench.tsx frontend/src/components/SceneList.tsx frontend/src/components/SceneInspector.tsx frontend/src/components/GenerationQueue.tsx frontend/src/App.tsx frontend/src/index.css tests/frontend/test_workbench_layout_contract.py
git commit -m "feat: add workbench three-column layout"
```

---

## M4：单镜交互、时间线、批量和导出

### Task 11: 实现提示词/旁白保存、候选确认和上传 UI

**Files:**
- Modify: `frontend/src/components/SceneInspector.tsx`
- Modify: `frontend/src/components/ProjectWorkbench.tsx`
- Modify: `frontend/src/lib/workbenchApi.ts`
- Create: `tests/frontend/test_workbench_inspector_contract.py`

- [ ] **Step 1: 写交互契约测试**

```python
def test_inspector_keeps_candidate_selection_explicit():
    source = Path("frontend/src/components/SceneInspector.tsx").read_text(encoding="utf-8")
    assert "使用此版本" in source
    assert "currentVersionId" in source
    assert "onRegenerateImage" in source
    assert "onUpload" in source
```

- [ ] **Step 2: 实现防抖保存和任务快照**

textarea 的 draft state 与 server state 分离；用户停止输入 500ms 后调用 `patchScene`。保存中显示 `保存中`，成功显示 `已保存`，错误显示重试。点击图片重生成时使用 draft prompt 的当前值调用 `regenerateImage(sceneId, {prompt})`，按钮在请求期间锁定。

候选列表必须将当前版本与新候选分开显示。`selectAssetVersion` 成功后刷新 project 并将预览切换到服务端返回的 current version，不能在请求前乐观覆盖。

`<input type="file" accept="image/png,image/jpeg,image/webp">` 上传到 scene endpoint，成功后将新 upload version 放入候选，不自动选择。

旁白保存后提供明确的“重新生成配音”按钮，调用 `regenerateTts`；不因文字保存自动产生付费任务。

- [ ] **Step 3: 运行前端测试**

运行：`uv run --extra dev pytest tests/frontend/test_workbench_inspector_contract.py -q`；`cd frontend && npx tsx --test src/lib/workbenchState.test.ts src/lib/workbenchApi.test.ts`。

预期：PASS；API 错误显示为可读文本，候选确认前当前图片不变。

- [ ] **Step 4: 提交单镜检查器**

```bash
git add frontend/src/components/SceneInspector.tsx frontend/src/components/ProjectWorkbench.tsx frontend/src/lib/workbenchApi.ts tests/frontend/test_workbench_inspector_contract.py
git commit -m "feat: add workbench scene inspector"
```

### Task 12: 实现单轨时间线、顺序和音频驱动时长

**Files:**
- Create: `frontend/src/components/WorkbenchTimeline.tsx`
- Modify: `frontend/src/components/ProjectWorkbench.tsx`
- Modify: `frontend/src/lib/workbenchState.ts`
- Modify: `api/schemas/workbench.py`
- Modify: `api/routers/projects.py`
- Create: `tests/frontend/test_workbench_timeline_contract.py`
- Modify: `tests/api/test_project_scene_mutations.py`

- [ ] **Step 1: 写顺序和时长失败测试**

```ts
test("dragging order produces contiguous positions", () => {
  assert.deepEqual(reorderScenes(fixture, ["s3", "s1", "s2"]).map((s) => s.position), [0, 1, 2]);
});

test("scene cannot be shortened below audio duration", () => {
  assert.equal(effectiveSceneDuration(3.5, -2), 3.5);
});
```

在 Python API 测试中断言 `manualHoldSeconds < 0` 返回 422，合法排序只保存一次事务。

- [ ] **Step 2: 实现 WorkbenchTimeline**

时间线只渲染当前项目 scene 的单轨 clips，clip 宽度使用 `max(48px, duration * zoom)`，由容器横向滚动，不让内容改变父布局宽度。拖拽使用原生 pointer events，不引入新 DnD 依赖；拖动结束调用 `reorderScenes` API。播放头和当前 scene 由 `selectedSceneId` 共享。

clip 右边缘只允许增加 `manualHoldSeconds`；尝试向左拖到音频结束点时吸附到最小值并显示提示。所有更新成功后刷新 project，失败则恢复本地顺序/时长。

- [ ] **Step 3: 实现后端排序/时长 PATCH**

`PATCH /api/projects/{project_id}/timeline` 请求：

```json
{
  "sceneIds": ["s3", "s1", "s2"],
  "holds": {"s3": 1.25}
}
```

后端验证 sceneIds 恰好是项目现有集合，position 重写为 0..N-1；holds 只接受非负 finite number，保存后返回完整 scene 摘要。

- [ ] **Step 4: 运行时间线测试**

运行：`uv run --extra dev pytest tests/api/test_project_scene_mutations.py -q`；`cd frontend && npx tsx --test src/lib/workbenchState.test.ts`；`uv run --extra dev pytest tests/frontend/test_workbench_timeline_contract.py -q`。

预期：PASS；顺序保存后重载不丢失，拖动不能制造负时长或重复 position。

- [ ] **Step 5: 提交时间线**

```bash
git add frontend/src/components/WorkbenchTimeline.tsx frontend/src/components/ProjectWorkbench.tsx frontend/src/lib/workbenchState.ts api/schemas/workbench.py api/routers/projects.py tests/frontend/test_workbench_timeline_contract.py tests/api/test_project_scene_mutations.py
git commit -m "feat: add workbench timeline editing"
```

### Task 13: 实现选中分镜的批量提示词和图片生成

**Files:**
- Modify: `api/schemas/workbench.py`
- Modify: `api/routers/projects.py`
- Modify: `pixelle_video/services/workbench_jobs.py`
- Modify: `frontend/src/components/SceneList.tsx`
- Modify: `frontend/src/components/ProjectWorkbench.tsx`
- Create: `tests/api/test_project_batch.py`
- Create: `tests/frontend/test_workbench_batch_contract.py`

- [ ] **Step 1: 写批量 API 测试**

```python
@pytest.mark.asyncio
async def test_batch_image_generation_creates_one_job_per_selected_scene(...):
    response = await submit_batch_image_generation(
        "p1", BatchImageRequest(scene_ids=["s1", "s2"], prompt_prefix="warm grain"), ...
    )
    assert len(response["jobs"]) == 2
    assert all(job["kind"] == "image" for job in response["jobs"])
```

测试还要断言重复 scene ID 被拒绝、空选择被拒绝、每个 job 的 prompt snapshot 是该 scene 原提示词加 prefix，候选完成后不自动选择。

- [ ] **Step 2: 实现批量请求和并发控制**

请求模型：`sceneIds: list[str]` 1–100、`promptPrefix: str` 最长 1000。路由校验所有 scene 属于 project 后，为每个 scene 单独创建 `WORKBENCH_IMAGE` task/job，使用 `asyncio.Semaphore(config.workbench.scene_concurrency)` 控制同时执行数量。一个失败只更新自己的 job，不把批次标为整体失败；响应返回全部 job。

- [ ] **Step 3: 实现前端多选工具条**

`SceneList` 添加 checkbox 和“选中 N 个”工具条；批量工具条只在 N>0 显示，包含提示词前缀输入、批量重新生成、清除选择。提交后保留选择但禁用重复提交，`GenerationQueue` 显示每项结果。不能加入批量旁白、批量时长或自动确认候选操作。

- [ ] **Step 4: 运行批量测试**

运行：`uv run --extra dev pytest tests/api/test_project_batch.py tests/frontend/test_workbench_batch_contract.py -q`；`cd frontend && npm run lint`。

预期：PASS；2 个 scene 产生 2 个独立 job，单项失败可以单项重试，当前版本引用不变。

- [ ] **Step 5: 提交批量能力**

```bash
git add api/schemas/workbench.py api/routers/projects.py pixelle_video/services/workbench_jobs.py frontend/src/components/SceneList.tsx frontend/src/components/ProjectWorkbench.tsx tests/api/test_project_batch.py tests/frontend/test_workbench_batch_contract.py
git commit -m "feat: add workbench batch image generation"
```

### Task 14: 将项目当前素材快照接入现有标准导出

**Files:**
- Modify: `api/schemas/workbench.py`
- Modify: `api/routers/projects.py`
- Modify: `pixelle_video/services/workbench_jobs.py`
- Modify: `pixelle_video/pipelines/standard.py`
- Modify: `pixelle_video/services/frame_processor.py`
- Modify: `api/schemas/video.py`
- Create: `tests/api/test_project_export.py`
- Create: `tests/pipelines/test_workbench_export_assets.py`

- [ ] **Step 1: 写导出快照失败测试**

```python
@pytest.mark.asyncio
async def test_export_snapshot_freezes_selected_versions(repository):
    response = await create_export("p1", ExportRequest(allow_incomplete=False), ...)
    snapshot = repository.get_export_revision(response["exportId"])

    repository.select_asset_version("p1", "s1", "new-version")

    assert snapshot.scene_assets["s1"] == "old-version"
```

另一个 pipeline 测试构造 `existing_scene_assets`，断言 `StandardPipeline.produce_assets` 不调用 fake `core.media`/`core.tts`，而是使用给定音频和图片继续 compose/segment。

- [ ] **Step 2: 实现导出检查和快照**

`POST /api/projects/{project_id}/exports` 先读取所有 scene，检查 current asset、audio、未完成 job；`allowIncomplete` 默认 false，缺项返回 409 并携带 `blockingScenes`。为 true 时只要每个 scene 有当前有效素材/音频就允许导出，并在响应中标记 omitted jobs。通过检查后在同一事务创建 `ExportRevision`，snapshot 至少包含：scene order、duration、current version IDs、media/audio relative paths、config snapshot。

- [ ] **Step 3: 增加 StandardPipeline 内部素材输入**

`_build_video_params` 不从公共请求读取路径。项目导出 job 直接调用 core pipeline 时传入内部参数：

```python
await core.generate_video(
    text=project.title,
    scenes=scene_inputs,
    existing_scene_assets={
        scene_id: {"image_path": image_path, "audio_path": audio_path}
        for scene_id, image_path, audio_path in snapshot
    },
    task_id=task_id,
    **config_snapshot,
)
```

`StandardPipeline.initialize_storyboard` 把内部映射按 scene position 写入 `StoryboardFrame`；`FrameProcessor` 在已有且通过路径安全校验的 image/audio 时跳过生成步骤，但仍执行 composition、subtitle 和 segment；`post_production` 继续使用现有 `VideoService.concat_videos`/BGM。任何 snapshot 路径不在项目根目录都直接失败。

- [ ] **Step 4: 运行导出测试**

运行：`uv run --extra dev pytest tests/api/test_project_export.py tests/pipelines/test_workbench_export_assets.py tests/services/test_frame_processor_composition.py -q`

预期：PASS；导出快照不随项目后续编辑变化，已有素材不会触发供应商调用，字幕/BGM/拼接路径仍被执行，非法路径被拒绝。

- [ ] **Step 5: 提交导出能力**

```bash
git add api/schemas/workbench.py api/routers/projects.py pixelle_video/services/workbench_jobs.py pixelle_video/pipelines/standard.py pixelle_video/services/frame_processor.py api/schemas/video.py tests/api/test_project_export.py tests/pipelines/test_workbench_export_assets.py
git commit -m "feat: export workbench asset snapshots"
```

### Task 15: 前端导出对话框和结果恢复

**Files:**
- Create: `frontend/src/components/ExportDialog.tsx`
- Modify: `frontend/src/components/ProjectWorkbench.tsx`
- Modify: `frontend/src/components/GenerationQueue.tsx`
- Modify: `frontend/src/lib/workbenchApi.ts`
- Modify: `frontend/src/types.ts`
- Create: `tests/frontend/test_workbench_export_contract.py`

- [ ] **Step 1: 写导出 UI 契约测试**

```python
def test_export_dialog_mentions_blocking_and_incomplete_export():
    source = Path("frontend/src/components/ExportDialog.tsx").read_text(encoding="utf-8")
    assert "导出检查" in source
    assert "只导出当前已完成版本" in source
    assert "二次确认" in source
```

- [ ] **Step 2: 实现检查面板**

`ExportDialog` 打开时使用当前 project 状态计算摘要；服务器返回 409 时展开 blocking scene 列表，并提供“定位分镜”回调。默认导出按钮在 blocking scene 非空时 disabled；“只导出当前已完成版本”必须由 checkbox 和二次确认按钮组成。提交成功后关闭对话框，`GenerationQueue` 添加 export job 并轮询 `/api/tasks/{taskId}`；完成后提供下载链接，失败后保留“重新导出”入口。

- [ ] **Step 3: 运行前端导出测试**

运行：`uv run --extra dev pytest tests/frontend/test_workbench_export_contract.py -q`；`cd frontend && npm run lint && npx tsx --test src/lib/workbenchApi.test.ts`。

预期：PASS；未完成项目不能误触发导出，导出失败不会清空当前 project 状态。

- [ ] **Step 4: 提交导出 UI**

```bash
git add frontend/src/components/ExportDialog.tsx frontend/src/components/ProjectWorkbench.tsx frontend/src/components/GenerationQueue.tsx frontend/src/lib/workbenchApi.ts frontend/src/types.ts tests/frontend/test_workbench_export_contract.py
git commit -m "feat: add workbench export confirmation"
```

---

## M5：历史任务项目化、浏览器验收和文档

### Task 16: 历史任务“继续精修”迁移

**Files:**
- Modify: `api/routers/history.py`
- Modify: `api/routers/projects.py`
- Modify: `frontend/src/components/HistoryList.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/workbenchApi.ts`
- Create: `tests/api/test_history_project_migration.py`
- Create: `tests/frontend/test_history_project_entry.py`

- [ ] **Step 1: 写迁移测试**

```python
@pytest.mark.asyncio
async def test_history_task_can_be_materialized_as_project_without_deleting_original(...):
    response = await create_project_from_history("legacy-task", ...)
    assert response["projectId"]
    assert await history_task_exists("legacy-task")
    assert len(response["scenes"]) == 2
```

- [ ] **Step 2: 实现只读历史到项目快照**

增加 `POST /api/projects/from-history/{task_id}`：读取现有 `HistoryManager` detail 和 `PersistenceService` storyboard，将每个有效 `image_path`/`audio_path` 复制到项目媒体目录并登记为 upload/legacy AssetVersion；配置写入项目 snapshot。原历史目录和 metadata 不删除、不改写。已迁移过的 task 通过一个 `source_history_task_id` 唯一索引返回既有 project，避免重复复制。

- [ ] **Step 3: 接入 HistoryList**

completed/failed history item 增加“打开工作台”按钮。点击后调用 migration endpoint，收到 project ID 后切换 `activeTab`，迁移失败只显示错误 Toast。下载、重试、删除旧历史行为保持不变。

- [ ] **Step 4: 运行迁移测试**

运行：`uv run --extra dev pytest tests/api/test_history_project_migration.py tests/frontend/test_history_project_entry.py tests/api/test_history_summary.py -q`

预期：PASS；旧历史仍可下载/删除，项目快照能读取场景和素材。

- [ ] **Step 5: 提交历史入口**

```bash
git add api/routers/history.py api/routers/projects.py frontend/src/components/HistoryList.tsx frontend/src/App.tsx frontend/src/lib/workbenchApi.ts tests/api/test_history_project_migration.py tests/frontend/test_history_project_entry.py
git commit -m "feat: open historical tasks in workbench"
```

### Task 17: 浏览器 smoke、窄屏抽屉和无真实生成验收

**Files:**
- Create: `tests/browser/project_workbench_smoke.py`
- Modify: `frontend/src/components/ProjectWorkbench.tsx`
- Modify: `frontend/src/components/SceneList.tsx`
- Modify: `frontend/src/components/SceneInspector.tsx`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: 写 smoke 流程**

浏览器测试使用 mock API 或只读 fixture server，不能点击真实付费生成。必须验证：

```python
page.goto(f"{BASE_URL}/?project=fixture-project")
page.get_by_role("button", name="分镜 03").click()
page.get_by_label("画面提示词").fill("new visual prompt")
assert page.get_by_text("已保存").is_visible()
page.get_by_role("button", name="重新生成").click()
assert page.get_by_text("生成中").is_visible()
page.get_by_role("button", name="使用此版本").click()
assert page.locator("[data-current-version='v2']").count() == 1
```

桌面视口用 1440x900，额外使用 390x844 验证侧栏/检查器抽屉、时间线横向滚动、导出按钮和焦点顺序。

- [ ] **Step 2: 实现 fixture 接入和响应式行为**

用 `VITE_API_TARGET` 指向测试 fixture API，或在 Python smoke 中拦截 `/api/projects`、scene PATCH、generation、export 请求。窄屏默认隐藏左栏和右栏，通过带 `aria-label` 的抽屉按钮打开；关闭时不销毁选中的 scene。所有可交互控件有可见 focus ring，错误通过 `aria-live="polite"` 显示。

- [ ] **Step 3: 运行浏览器 smoke**

运行：`uv run python tests/browser/project_workbench_smoke.py`

预期：打印 `project workbench browser smoke passed`，无 console error、page error、横向页面溢出或遮挡关键按钮。

- [ ] **Step 4: 提交浏览器验收**

```bash
git add tests/browser/project_workbench_smoke.py frontend/src/components/ProjectWorkbench.tsx frontend/src/components/SceneList.tsx frontend/src/components/SceneInspector.tsx frontend/src/index.css
git commit -m "test: add project workbench browser smoke"
```

### Task 18: 文档、全量回归和发布检查

**Files:**
- Modify: `README.md`
- Modify: `README_EN.md`
- Modify: `docs/zh/user-guide/web-ui.md`
- Modify: `docs/en/user-guide/web-ui.md`
- Modify: `tests/frontend/test_quick_create_workflow.py`
- Modify: `tests/frontend/test_history_state.py`

- [ ] **Step 1: 同步用户文档**

中文文档必须说明：快捷创作默认进入工作台、直接成片旁路、30–100 分镜、候选版本确认、项目内上传、音频驱动时长、批量图片操作、导出前检查和历史任务继续精修。英文文档同步同一语义，不声称已有素材库、协作或完整多轨剪辑。

- [ ] **Step 2: 运行完整回归**

按顺序运行：

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check api pixelle_video tests
cd frontend
npm run lint
npx tsx --test src/lib/*.test.ts
npm run build
cd ..
git diff --check
```

预期：所有 pytest、ruff、TypeScript、Node tests 和 Vite build 通过；既有 QuickCreate、历史、任务取消、字幕和媒体服务测试不回归。

- [ ] **Step 3: 做最终差异审计**

确认 `git status --short` 中只有本计划涉及的实现/测试/文档文件；确认 `data/workbench`、输出媒体和本地配置未被加入 git；确认没有 `.env`、API key、真实生成结果或浏览器截图进入提交。

- [ ] **Step 4: 最终提交**

```bash
git add README.md README_EN.md docs/zh/user-guide/web-ui.md docs/en/user-guide/web-ui.md tests/frontend/test_quick_create_workflow.py tests/frontend/test_history_state.py
git commit -m "docs: document AI editing workbench"
```

---

## 验收清单

实现完成后，必须逐项确认：

- [ ] QuickCreate 默认创建项目并进入 `project-workbench`；“直接生成成片”仍调用旧 `/api/video/generate/async`。
- [ ] 100 个显式分镜可以创建、滚动、保存和重载；101 个被拒绝并给出可读错误。
- [ ] 项目打开后图片/TTS 任务渐进显示；单项失败、取消、重试不影响其他分镜。
- [ ] 提示词重生成创建新候选，不覆盖当前版本；“使用此版本”后才切换预览和导出引用。
- [ ] 上传图片安全地复制到项目目录，路径逃逸和无效图片被拒绝。
- [ ] 旁白重生成只影响当前 scene 的 TTS、字幕对齐和音频驱动时长。
- [ ] 时间线只允许增加画面停留，不允许短于音频；排序持久化为连续 positions。
- [ ] 多选 scene 可批量添加风格前缀并独立生成候选，不批量改旁白/时长。
- [ ] 导出前阻止缺素材项目；允许 incomplete export 时必须二次确认；导出使用不可变快照。
- [ ] 导出复用现有字幕、BGM、FFmpeg 和模板合成，不在每次图片修改时重渲染整片。
- [ ] 旧 history 可以 materialize 为项目，原 history 不被删除或覆盖。
- [ ] 桌面和 390px 视口无关键控件遮挡、横向溢出或无标签输入。
- [ ] 全量 Python、TypeScript、Node、Vite 和浏览器回归通过。

## 计划自审记录

- **规格覆盖：** 项目生命周期对应 Task 4–5；版本候选对应 Task 6/11；项目内上传对应 Task 2/6；单镜 TTS 对应 Task 6/11；三栏布局对应 Task 10；音频驱动时长对应 Task 12；批量图片对应 Task 13；导出快照对应 Task 14–15；历史恢复对应 Task 16；响应式和测试对应 Task 17–18。
- **完整性扫描：** 未发现不完整步骤或未定义任务；每个步骤都有文件、命令、预期结果或可执行接口。
- **类型一致性：** 后端统一使用 `project_id/scene_id/version_id/job_id/export_id`，API camelCase 只在 Pydantic 边界转换；前端类型与 API 响应字段一一对应；`GenerationKind` 和 `TaskType` 的值在 Task 1/3/5/8/14 中保持一致。
- **范围检查：** 不引入账号、Redis、Celery、完整多轨、跨项目素材库或新媒体供应商；所有生成和导出都复用现有服务。
