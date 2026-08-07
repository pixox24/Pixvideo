# 项目级生成工作台实施计划

> 状态：待审阅。本文档只描述实施方案，不包含本轮代码实现。
>
> 设计依据：docs/superpowers/specs/2026-08-07-project-generation-workbench-design.md

## 目标与边界

把当前按场景单独提交的图片、TTS 和导出任务，扩展为一个可恢复的项目级生产运行。用户在工作台确认参数后点击一次“开始生成”，系统按时间线顺序扫描全部场景，跳过有效素材，补齐缺失或过期素材，并在 TTS 完成后立即把真实音频时长写入时间线。图片完成后，如果场景没有当前图片则自动成为当前版本；如果已有当前图片，则保存为候选版本，等待用户明确确认。

第一版只实现项目内串行执行。暂停、取消、失败继续、仅重试失败项、服务重启恢复、前端一秒轮询和逐场景回填属于第一版范围。项目内并发、SSE/WebSocket、自动重试、多轨时间线、跨项目素材库和协作权限不属于第一版。

保留现有快捷创作直生成路径、单场景图片/TTS 操作、素材上传、时间线排序/停留时长编辑和导出快照。新增项目级运行是它们之上的编排层，不替换已有单场景接口。

## 执行约束

1. 实施前从 main 创建独立 worktree 和分支。根工作区中的任何未提交文件都视为用户修改，不得 reset、checkout、clean、删除或混入提交。
2. 建议的隔离目录和分支为 .worktrees/project-generation-workbench 与 codex/project-generation-workbench。
3. 每个里程碑必须按“先测试、再实现、再回归、再提交”的顺序完成；里程碑出口检查通过后停止，等待用户确认再进入下一个里程碑。
4. 真实 LLM、TTS、图片、FFmpeg 服务不用于单元测试。测试使用 fake core、fake media store、临时 SQLite 和临时媒体目录。
5. 数据库写操作必须是单次事务；路径只保存项目根目录内的相对路径；运行快照必须是不可变 JSON。
6. 前端状态更新必须可重复执行，轮询清理必须在组件卸载、项目切换和运行结束时发生。

## 实施前准备

在根仓库执行以下只读检查，确认当前分支和 worktree 状态：

    git status --short --branch
    git worktree list
    git log -1 --oneline

如果目标 worktree 尚不存在，从 main 创建：

    git worktree add -b codex/project-generation-workbench .worktrees/project-generation-workbench main
    Set-Location .worktrees/project-generation-workbench

如果目标目录或分支已经存在，只能先用 git worktree list 和 git status 确认归属，再复用；不得覆盖已有目录。每个里程碑的提交只允许包含该里程碑列出的文件。

## 当前代码边界

- pixelle_video/models/workbench.py 已有 Project、Scene、AssetVersion、GenerationJob、ExportRevision。
- pixelle_video/services/workbench_repository.py 使用 SQLite、WAL 和 CREATE TABLE IF NOT EXISTS，已经提供项目、场景、版本、单场景任务和导出快照的 CRUD。
- pixelle_video/services/workbench_jobs.py 负责单场景 TTS、图片、导出；run_scene_job 当前按 TTS 再图片执行，但没有项目级运行状态。
- api/tasks/manager.py 是进程内 TaskManager；重启后任务对象消失，因此 GenerationRun 必须独立持久化。
- api/routers/projects.py 已有项目、场景、版本、批量图片和导出路由，但 _response 当前把 jobs 固定为 []。
- api/schemas/workbench.py 使用 Pydantic v2 和 camelCase alias。
- frontend/src/components/ProjectWorkbench.tsx 一次性 fetchProject，现有 GenerationQueue 只展示单场景/导出任务。
- frontend/src/lib/workbenchState.ts 已有纯函数测试，可继续放置运行状态 reducer 的无 DOM 测试。

## 状态模型与不变量

### GenerationRun

项目级一次生产运行。字段固定为：

    run_id
    project_id
    task_id
    status
    parameter_snapshot_json
    current_scene_id
    total_count
    completed_count
    skipped_count
    failed_count
    candidate_review_count
    pause_requested
    cancel_requested
    created_at
    updated_at
    error

run status 只允许以下值：

- queued：已创建，尚未开始调度。
- running：正在执行一个场景。
- paused：当前请求已结束，调度器暂不启动下一个场景。
- completed：所有计划项完成或跳过，且没有失败项。
- completed_with_failures：所有计划项已结束，但至少一项失败。
- cancelled：取消请求已生效，剩余未启动项标记为 cancelled。
- failed：运行级异常导致无法继续，例如运行快照损坏或数据库不可写。

### GenerationRunItem

一个运行中的场景执行快照。字段固定为：

    item_id
    run_id
    scene_id
    position
    narration_snapshot
    prompt_snapshot
    narration_fingerprint
    image_fingerprint
    tts_status
    image_status
    status
    skip_reason
    candidate_version_id
    error
    created_at
    updated_at

item status 允许 queued、running_tts、running_image、completed、skipped、failed、cancelled、candidate_review。tts_status 和 image_status 只允许 pending、running、completed、skipped、failed、cancelled。

状态不变量：

- 一个项目同一时间最多有一个非终态运行。创建接口必须返回 409，并携带现有 runId。
- 一个运行只能消费自己的 item 快照，不能从数据库重新读取等待场景的最新提示词或旁白。
- tts_status 变为 completed 后，才允许建立或更新该场景时间线片段。
- image 生成成功但场景已有 current_version_id 时，item 必须进入 candidate_review，不能自动替换 current_version_id。
- 单项 failed 不得阻塞 position 更大的 queued 项。
- pause_requested 和 cancel_requested 是协作信号，不强制终止外部 TTS/图片请求。

## Milestone 0：隔离分支与测试夹具

### 目的

建立实现分支、测试入口和 fake provider，确保后续每个里程碑都能独立验证，不触碰真实外部服务。

### 文件

- 新建 tests/services/test_project_generation_fixtures.py（如需要共享 fixture）。
- 修改 tests/conftest.py（仅在现有 fixture 组织方式确实需要时）。
- 不修改产品运行代码。

### 步骤

- [ ] 确认目标 worktree 只包含 main 已有内容，记录根工作区 dirty 文件清单。
- [ ] 为临时项目目录、SQLite、fake TTS、fake image provider 和可控音频时长建立 fixture。
- [ ] fake provider 支持按 scene_id 注入成功、失败、延迟和取消后完成四种结果。
- [ ] 为运行测试增加可控时钟或直接通过 repository 更新时间字段，避免使用长时间 sleep。
- [ ] 运行既有 workbench 测试，确认基线仍通过。

### 验证命令

    uv run --extra dev pytest tests/models/test_workbench.py tests/services/test_workbench_repository.py tests/services/test_workbench_jobs.py -q

### 里程碑出口

基线测试通过，fake provider 可以让测试确定性地模拟至少两个场景的顺序、失败和延迟。提交：

    git add tests/services/test_project_generation_fixtures.py tests/conftest.py
    git commit -m "test: add project generation fixtures"

只在相关文件实际存在或修改时执行 git add；不要为了提交空变更创建提交。

## Milestone 1：运行模型、SQLite schema 与状态持久化

### 目的

使项目级运行和运行项在服务重启后仍可读取，并为后续调度器提供原子状态更新接口。

### 文件

- 修改 pixelle_video/models/workbench.py。
- 修改 pixelle_video/services/workbench_repository.py。
- 新建 tests/models/test_project_generation.py。
- 新建 tests/services/test_project_generation_repository.py。

### 模型实现

- 新增 GenerationRunStatus、GenerationRunItemStatus、GenerationPhase 枚举，枚举值与本计划状态模型完全一致。
- 新增 GenerationRun 和 GenerationRunItem dataclass。所有时间字段使用现有 utc_now；所有 ID 使用 uuid4().hex。
- 为 GenerationRun 增加 is_terminal 属性或纯函数，终态集合只能是 completed、completed_with_failures、cancelled、failed。
- 为 GenerationRunItem 增加 is_terminal 属性，candidate_review 是可人工处理的终态，不应被调度器重复执行。
- GenerationJob 继续代表单个底层任务；GenerationRun 通过 task_id 关联 TaskManager 父任务，不改变旧任务表含义。

### SQLite 迁移

在现有 _initialize_schema 中追加 CREATE TABLE IF NOT EXISTS，并增加必要索引：

    generation_runs(
      run_id TEXT PRIMARY KEY,
      project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
      task_id TEXT NOT NULL UNIQUE,
      status TEXT NOT NULL,
      parameter_snapshot_json TEXT NOT NULL,
      current_scene_id TEXT,
      total_count INTEGER NOT NULL DEFAULT 0,
      completed_count INTEGER NOT NULL DEFAULT 0,
      skipped_count INTEGER NOT NULL DEFAULT 0,
      failed_count INTEGER NOT NULL DEFAULT 0,
      candidate_review_count INTEGER NOT NULL DEFAULT 0,
      pause_requested INTEGER NOT NULL DEFAULT 0,
      cancel_requested INTEGER NOT NULL DEFAULT 0,
      error TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )

    generation_run_items(
      item_id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL REFERENCES generation_runs(run_id) ON DELETE CASCADE,
      scene_id TEXT NOT NULL REFERENCES scenes(scene_id) ON DELETE CASCADE,
      position INTEGER NOT NULL,
      narration_snapshot TEXT NOT NULL,
      prompt_snapshot TEXT NOT NULL,
      narration_fingerprint TEXT NOT NULL,
      image_fingerprint TEXT NOT NULL,
      tts_status TEXT NOT NULL,
      image_status TEXT NOT NULL,
      status TEXT NOT NULL,
      skip_reason TEXT,
      candidate_version_id TEXT,
      error TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(run_id, scene_id)
    )

    CREATE INDEX IF NOT EXISTS idx_generation_runs_project_status
      ON generation_runs(project_id, status)
    CREATE INDEX IF NOT EXISTS idx_generation_run_items_run_position
      ON generation_run_items(run_id, position)

为现有 scenes 表增加 image_fingerprint 和 audio_fingerprint 列。SQLite 迁移使用 PRAGMA table_info 检查后再执行 ALTER TABLE，不能依赖重复 ALTER TABLE 被忽略。旧项目的两列默认 NULL，视为 stale 或 missing。

### Repository API

新增以下方法，方法内部都使用事务：

- create_generation_run(run, items)
- get_generation_run(run_id)
- get_active_generation_run(project_id)
- list_generation_runs(project_id, limit=20)
- list_generation_run_items(run_id)
- get_generation_run_item(item_id)
- update_generation_run(run_id, **changes)
- update_generation_run_item(item_id, **changes)
- mark_remaining_run_items_cancelled(run_id)
- recompute_generation_run_counts(run_id)
- list_generation_jobs(project_id, include_terminal=True)

运行更新必须把枚举转换为字符串，把布尔转换为 0/1，并在同一事务内更新 updated_at。get 方法返回 dataclass，而不是 sqlite3.Row。

### 测试先行清单

- [ ] 模型默认值、枚举值和 terminal 判断稳定。
- [ ] 新数据库包含两张运行表、两个索引和 fingerprint 列。
- [ ] 旧版只有原有表的数据库经过初始化后可增加新列，原有项目仍可读取。
- [ ] run、items、计数器和请求标志写入后关闭连接，再开连接仍能完整读取。
- [ ] 同一 run 不能重复插入同一 scene，活动运行查询只返回非终态运行。
- [ ] 回滚测试证明 create_generation_run 的 run 或任一 item 写失败时不会留下半条运行。

### 验证与提交

    uv run --extra dev pytest tests/models/test_project_generation.py tests/services/test_project_generation_repository.py tests/services/test_workbench_repository.py -q

    git add pixelle_video/models/workbench.py pixelle_video/services/workbench_repository.py tests/models/test_project_generation.py tests/services/test_project_generation_repository.py
    git commit -m "feat: persist project generation runs"

## Milestone 2：规划器、指纹和素材新鲜度

### 目的

在不调用外部模型的情况下，把当前项目状态冻结为 GenerationRun 和有明确跳过原因的 GenerationRunItem。

### 文件

- 新建 pixelle_video/services/workbench_generation.py。
- 修改 pixelle_video/models/workbench.py（仅补充规划所需的轻量值对象时）。
- 修改 pixelle_video/services/workbench_repository.py（如需要原子读取场景及版本）。
- 新建 tests/services/test_workbench_generation_planner.py。

### 指纹规则

实现 canonical_json 和 sha256_fingerprint 纯函数。字典键排序、列表顺序保留、字符串 trim 后参与 hash，不能把 API key、临时路径或时间戳放入指纹。

- narration_fingerprint = text + tts provider + voice + speed + emotion + tts model。
- image_fingerprint = visual prompt + image model/workflow + mediaWidth + mediaHeight + image style/prefix 参数。
- 参数来源是运行开始时的项目 config 与生成设置；运行 snapshot 必须保存脱敏后的完整参数。

图片版本的 parameters_json 中保存 image_fingerprint；场景的 audio_fingerprint 保存 narration_fingerprint。没有 fingerprint 的旧素材视为 stale。文件不存在、路径越界或无法读取也视为 missing。

### Planner 接口

建议提供：

- build_parameter_snapshot(project, config_override=None) -> dict
- plan_items(project, scenes, parameter_snapshot, scene_ids=None) -> list[GenerationRunItem]
- plan_run(project_id, scope="incomplete", scene_ids=None) -> GenerationRun
- plan_retry_failed(run_id) -> GenerationRun

默认 scope 是全部场景，但 item 只对缺失或过期的 TTS/图片执行；已有有效 TTS 和图片的场景生成 skipped item。scene_ids 只允许属于项目的 ID。retry_failed 只选指定旧运行中 status=failed 的场景，并使用新运行开始时的当前项目配置和场景内容；不复用旧运行的 prompt 快照。

### 规划判定

- TTS ready：audio_relative_path 存在且文件存在，audio_fingerprint 等于预期 narration_fingerprint。
- Image ready：current_version_id 存在，版本文件存在，版本 parameters.imageFingerprint 等于预期 image_fingerprint。
- 有 current image 但 prompt 已变化：image item 进入 queued，生成成功后 candidate_review。
- 有上传图片且没有 image_fingerprint：第一版将其视为 ready，仅在用户显式修改提示词或运行配置后重新生成；上传素材不要求反推 AI 指纹。
- TTS ready 但 image stale：不重新生成 TTS，先建立已有音频对应的时间线时长，再生成图片。
- image ready 但 TTS stale：先生成 TTS、更新时长，再跳过图片。

### 测试先行清单

- [ ] 相同参数产生相同 fingerprint，参数顺序不影响结果。
- [ ] 旁白变化只使音频 stale，提示词变化只使图片 stale。
- [ ] 配置变化使对应阶段 stale，临时路径和密钥不影响 fingerprint。
- [ ] 有效素材被规划为 skipped，并带 skip_reason=up_to_date。
- [ ] 缺失音频、缺失图片、失效路径和旧素材被规划为 queued。
- [ ] 有旧 current image 时，planner 不改变 current_version_id。
- [ ] retry_failed 只创建失败场景的 items，并保留正确 position 顺序。
- [ ] 运行 snapshot 与后续项目编辑互不共享可变对象。

### 验证与提交

    uv run --extra dev pytest tests/services/test_workbench_generation_planner.py -q

    git add pixelle_video/services/workbench_generation.py pixelle_video/models/workbench.py pixelle_video/services/workbench_repository.py tests/services/test_workbench_generation_planner.py
    git commit -m "feat: plan project generation from asset freshness"

## Milestone 3：串行编排、暂停取消和重启恢复

### 目的

让规划出的运行真正按 position 顺序执行 TTS -> 时间线片段 -> 图片，并在单项失败后继续后续场景。

### 文件

- 新建 pixelle_video/services/project_generation_service.py。
- 修改 pixelle_video/services/workbench_jobs.py。
- 修改 pixelle_video/service.py。
- 修改 api/tasks/models.py。
- 修改 api/tasks/manager.py（只增加父任务类型或安全的状态读取，不改变旧任务语义）。
- 修改 api/app.py。
- 新建 tests/services/test_project_generation_service.py。
- 新建 tests/api/test_project_generation_lifecycle.py。

### 服务边界

ProjectGenerationService 负责运行生命周期、快照、调度和恢复；WorkbenchJobService 负责一次 TTS 或图片的外部调用与媒体落盘。为避免现有 run_tts_job/run_image_job 的场景状态更新覆盖父运行状态，先从 WorkbenchJobService 提取不负责 run 状态的内部原语：

- generate_tts_asset(project_id, scene_id, task_id, narration_snapshot, narration_fingerprint)
- generate_image_asset(project_id, scene_id, task_id, prompt_snapshot, image_fingerprint)

保留 run_tts_job、run_image_job、run_scene_job 的旧 API，并让它们调用内部原语，以保证现有单场景接口兼容。内部原语必须返回 audio_relative_path、duration_seconds、version_id、is_candidate 等结构化结果。

ProjectGenerationService 的核心方法：

- start(project_id, parameter_override=None, scene_ids=None) -> GenerationRun
- run(run_id) -> None
- request_pause(run_id)
- request_resume(run_id)
- request_cancel(run_id)
- retry_failed(run_id) -> GenerationRun
- resume_active_runs() -> list[str]
- assert_scene_editable(project_id, scene_id)

### 调度算法

1. start 在一个事务中检查活动运行、读取项目和场景、构造 parameter_snapshot、生成 items、插入 GenerationRun，并创建 TaskType.WORKBENCH_PROJECT_RUN 父任务。
2. run 每次从 position 最小的非终态 item 开始；设置 current_scene_id 和 item.status=running_tts。
3. 每次开始新 item 前读取 pause_requested/cancel_requested。pause 时保持 item queued；cancel 时把当前外部请求等待到自然返回，再将未启动项标记 cancelled。
4. TTS ready 时写 tts_status=skipped，并从现有音频读取真实时长；TTS 缺失或 stale 时调用 generate_tts_asset，成功后写 audio_fingerprint、duration_seconds 和时间线所需场景状态。
5. TTS 阶段成功后立即把 scene duration_seconds 更新为 max(audio duration, audio duration + manual hold)，然后再进入图片阶段。
6. 图片 ready 时写 image_status=skipped；否则调用 generate_image_asset。没有 current_version_id 时选择新版本；已有 current_version_id 时只写 candidate_version_id 并把 item.status 设为 candidate_review。
7. 成功、跳过或 candidate_review 都继续下一个 item。异常只捕获到当前 item，写 error、failed 状态和 parent 计数，然后继续调度。
8. 所有 item 终态后，按 failed_count 选择 completed 或 completed_with_failures；cancel_requested 优先生成 cancelled。父 TaskManager 任务和 GenerationRun 必须同步为同一终态。

### 暂停、取消和恢复

- pause 只设置 pause_requested；当前外部请求返回后 run 进入 paused。resume 清除 pause_requested 并重新提交 run 协程。
- cancel 只设置 cancel_requested；不调用外部 SDK 的强杀接口。当前请求完成后，剩余 queued 项变为 cancelled，运行进入 cancelled。
- 服务启动后，resume_active_runs 查询 queued/running/paused 且未 cancel 的运行。running 项重新从其未完成阶段继续；已完成的 TTS 或图片依据持久化 fingerprint 不重复生成。
- TaskManager stop 不得清除 GenerationRun 数据。进程内 future 消失是可接受的，下一次启动由 resume_active_runs 接管。
- 一个 run 协程必须使用 asyncio.Lock 或 repository 的活动运行检查，避免 resume 与 API resume 重复启动。

### 编辑锁

assert_scene_editable 在以下情况下拒绝修改当前 scene：

- 该场景属于活动运行且 item.status 为 running_tts 或 running_image。
- 该场景是当前外部请求尚未返回的场景。

返回 409，detail 中包含 runId 和 sceneId。等待中的场景仍可编辑，修改只影响下一次运行，不回写当前 run item 快照。单场景生成、上传和版本选择对活动中的当前场景同样返回 409，其他场景保持现有行为。

### 测试先行清单

- [ ] 两个场景严格按 position 执行，每个场景严格 TTS 完成后才调用图片。
- [ ] TTS 完成会写入真实 duration，并立即更新 timeline scene。
- [ ] 现有 current image 时新图片保存为 candidate，不替换 current；没有 current image 时自动选择。
- [ ] 有效素材只产生 skipped，不调用 fake provider。
- [ ] 第一个场景失败后第二个场景仍执行，运行最终为 completed_with_failures。
- [ ] pause 不启动下一个场景；resume 从暂停项继续。
- [ ] cancel 不强杀 fake provider，但当前请求返回后剩余项为 cancelled。
- [ ] 服务重启模拟中，running_tts/running_image 项可依据 fingerprint 恢复，已完成阶段不重复调用。
- [ ] 活动当前场景被编辑时返回 409，等待场景编辑不改变运行快照。
- [ ] TaskManager 父任务和 GenerationRun 的终态、错误信息和计数一致。

### 验证与提交

    uv run --extra dev pytest tests/services/test_project_generation_service.py tests/api/test_project_generation_lifecycle.py tests/services/test_workbench_jobs.py -q

    git add pixelle_video/services/project_generation_service.py pixelle_video/services/workbench_jobs.py pixelle_video/service.py api/tasks/models.py api/tasks/manager.py api/app.py tests/services/test_project_generation_service.py tests/api/test_project_generation_lifecycle.py
    git commit -m "feat: orchestrate sequential project generation"

## Milestone 4：API 契约与项目响应

### 目的

提供创建、查询、暂停、恢复、取消和失败重试接口，并让现有项目响应反映持久化任务和素材新鲜度。

### 文件

- 修改 api/schemas/workbench.py。
- 修改 api/routers/projects.py。
- 修改 pixelle_video/services/workbench_repository.py（如需响应查询）。
- 新建 tests/api/test_project_generation_api.py。
- 修改 tests/api/test_projects.py 和现有 project mutation tests。

### Schema

新增请求：

- GenerationRunCreateRequest：scene_ids 可选，config_override 可选；空请求表示全部场景。

新增响应：

- GenerationRunResponse：runId、projectId、taskId、status、currentSceneId、totalCount、completedCount、skippedCount、failedCount、candidateReviewCount、pauseRequested、cancelRequested、error、createdAt、updatedAt、items。
- GenerationRunItemResponse：itemId、sceneId、position、status、phase、ttsStatus、imageStatus、skipReason、candidateVersionId、error、updatedAt。
- GenerationRunActionResponse：复用 GenerationRunResponse，保证 pause/resume/cancel/retry 的返回结构一致。

ProjectSceneResponse 增加 generationState：

    {
      image: "ready" | "missing" | "stale",
      audio: "ready" | "missing" | "stale",
      candidateCount: number
    }

新增路由：

    POST /api/projects/{project_id}/generation-runs
    GET  /api/projects/{project_id}/generation-runs/{run_id}
    POST /api/projects/{project_id}/generation-runs/{run_id}/pause
    POST /api/projects/{project_id}/generation-runs/{run_id}/resume
    POST /api/projects/{project_id}/generation-runs/{run_id}/cancel
    POST /api/projects/{project_id}/generation-runs/{run_id}/retry-failed

创建和 retry-failed 返回 202。不存在项目或运行返回 404；运行属于其他项目也返回 404，不泄露运行存在性；活动运行冲突返回 409，并返回 currentRunId；非法状态动作返回 409，并包含 allowedActions。

_response 必须通过 list_generation_jobs 返回现有任务，不能继续固定 jobs=[]。生成运行可以作为独立 run 字段返回，也可以作为 jobs 中 kind=scene 的父任务，但前端契约只依赖 GenerationRunResponse。

### 现有路由调整

- update_scene、regenerate_image、regenerate_tts、upload_scene_asset、select_asset_version 在写入前调用 assert_scene_editable。
- update_scene 修改 narration 或 visualPrompt 后不直接生成；generationState 在下一次 fetch 中显示 stale。
- create_export 保持使用 current 版本；当存在 candidate_review 时在 409 或成功响应前的检查结果中明确 warning，但默认不选候选。
- 现有单场景 API 返回格式和 status code 不变。

### 测试先行清单

- [ ] 创建运行返回 runId、202 和正确的初始 item 状态。
- [ ] 查询运行返回 camelCase 字段、完整 items、计数和当前场景。
- [ ] pause/resume/cancel 只允许对应状态，重复调用返回 409。
- [ ] retry-failed 只创建失败场景的新运行；存在活动运行时返回 409。
- [ ] 跨项目 runId 访问返回 404。
- [ ] ProjectResponse jobs 不再丢失，generationState 对 missing/stale/ready/candidate 正确。
- [ ] 活动场景编辑被锁，等待场景编辑成功。
- [ ] 导出仍默认使用 current version，并返回候选未确认 warning。

### 验证与提交

    uv run --extra dev pytest tests/api/test_project_generation_api.py tests/api/test_projects.py tests/api/test_project_scene_mutations.py tests/api/test_project_export.py -q

    git add api/schemas/workbench.py api/routers/projects.py pixelle_video/services/workbench_repository.py tests/api/test_project_generation_api.py tests/api/test_projects.py tests/api/test_project_scene_mutations.py tests/api/test_project_export.py
    git commit -m "feat: expose project generation run API"

## Milestone 5：前端运行控制、轮询和逐场景回填

### 目的

把工作台从“手动提交若干任务”升级为用户可理解的项目级生产界面，同时保留单场景编辑能力。

### 文件

- 修改 frontend/src/types.ts。
- 修改 frontend/src/lib/workbenchApi.ts。
- 新建 frontend/src/lib/projectGenerationState.ts。
- 新建 frontend/src/lib/projectGenerationState.test.ts。
- 新建 frontend/src/components/GenerationRunPanel.tsx。
- 修改 frontend/src/components/ProjectWorkbench.tsx。
- 修改 frontend/src/components/SceneList.tsx。
- 修改 frontend/src/components/SceneInspector.tsx。
- 修改 frontend/src/components/WorkbenchTimeline.tsx。
- 修改 frontend/src/components/ExportDialog.tsx。
- 修改 tests/frontend/test_workbench_contract.py。
- 修改 tests/browser/project_workbench_smoke.py。

### 前端类型与 API

在 types.ts 增加 GenerationRunStatus、GenerationRunItemStatus、GenerationState、GenerationRun、GenerationRunItem、GenerationRunActionResponse。所有 API 函数集中放在 workbenchApi.ts：

- startGenerationRun
- fetchGenerationRun
- pauseGenerationRun
- resumeGenerationRun
- cancelGenerationRun
- retryFailedGeneration

requestJson 的错误对象必须保留 HTTP status、detail、currentRunId 和 blockingScenes，供 409 状态提示使用。

### 纯状态 reducer

projectGenerationState.ts 只处理不可变状态，不触碰 React 或网络。状态至少包含 run、polling、lastProjectUpdatedAt、error、actionBusy。纯函数包括：

- initialGenerationState
- reduceRunStarted
- reduceRunFetched
- reduceRunActionStarted
- reduceRunActionFailed
- shouldRefreshProject
- isRunTerminal

规则：

- 相同 run 快照重复轮询不得产生额外状态变化。
- run.updatedAt 变更或 item 状态变更时才刷新计数。
- terminal 运行停止轮询；candidate_review 仍显示为完成后待审核，不算 failed。
- 项目更新时间变化时调用 fetchProject，逐场景更新 timeline，不重置 selectedSceneId。

### UI 行为

GenerationRunPanel 放在工作台顶部参数区域：

- idle：显示待生成数、过期数、候选待确认数和主按钮“开始生成”。
- running：显示总进度、当前场景编号和阶段；显示“暂停”“取消”。当前场景的旁白/提示词/单场景生成按钮锁定，其他场景可编辑。
- paused：显示“继续生成”和“取消”。
- completed：显示成功、跳过、候选待确认、失败统计；没有失败时隐藏重试按钮。
- completed_with_failures：显示失败列表和“仅重试失败项”。
- cancelled/failed：显示原因和可执行动作，不自动重启。

开始生成按钮默认不带 sceneIds；只传用户明确选择的设置覆盖。活动运行时按钮禁用，409 时定位已有运行而不是创建第二个运行。

SceneList 使用 generationState 和 run item 状态显示 queued、TTS、图片、候选、失败、完成图标；当前运行场景加锁标记。列表行高度固定，避免状态文字导致时间线跳动。

WorkbenchTimeline 在 TTS 完成后立即使用 durationSeconds 渲染片段；等待中的场景保留固定占位尺寸；图片缩略图更新不能改变轨道高度或其他片段位置。候选版本显示 badge，但不替换 current 预览。

SceneInspector 在 locked=true 时禁用文本框、保存、上传、单场景生成和版本切换；等待场景仍可编辑。保存失败必须恢复可编辑状态并显示错误。

ExportDialog 在有 candidateReviewCount 时增加未确认候选警告，导出预览和最终提交继续使用 currentVersionId；不提供隐式切换候选。

### 轮询实现

ProjectWorkbench 维护 activeRunId。开始运行成功后立即 fetchGenerationRun，并以 1000ms setInterval 轮询；请求进行中不得并发发起下一次请求。项目切换、组件卸载、run 终态和显式取消都清理 timer。只有 run.updatedAt 或 item.updatedAt 变化时才 fetchProject，防止不必要的整个工作台重绘。

### 测试先行清单

- [ ] reducer 覆盖 idle -> running -> paused -> running -> completed。
- [ ] completed_with_failures 显示 retry action，cancelled 不显示 retry。
- [ ] 重复轮询不会重复计数或丢失 selectedSceneId。
- [ ] run 时间戳变化会触发 project refresh，未变化不会。
- [ ] active scene 锁定，waiting scene 可编辑。
- [ ] 时间线在 TTS 完成后回填真实 duration，图片候选不替换 current 预览。
- [ ] start/pause/resume/cancel/retry API 被正确调用，网络错误显示可操作提示。
- [ ] 现有单场景重生成、上传、版本确认、导出流程没有回归。

### 验证与提交

    Set-Location frontend
    npm run lint
    node --test --import tsx src/lib/workbenchState.test.ts src/lib/projectGenerationState.test.ts
    npm run build
    Set-Location ..
    uv run --extra dev pytest tests/frontend/test_workbench_contract.py tests/browser/project_workbench_smoke.py -q

    git add frontend/src/types.ts frontend/src/lib/workbenchApi.ts frontend/src/lib/projectGenerationState.ts frontend/src/lib/projectGenerationState.test.ts frontend/src/components/GenerationRunPanel.tsx frontend/src/components/ProjectWorkbench.tsx frontend/src/components/SceneList.tsx frontend/src/components/SceneInspector.tsx frontend/src/components/WorkbenchTimeline.tsx frontend/src/components/ExportDialog.tsx tests/frontend/test_workbench_contract.py tests/browser/project_workbench_smoke.py
    git commit -m "feat: add project generation controls to workbench"

## Milestone 6：端到端验收、恢复演练和文档

### 目的

验证用户从项目创建到逐场景生成、候选确认和导出的完整路径，并验证重启恢复与错误边界。

### 文件

- 新建 tests/integration/test_project_generation_e2e.py。
- 修改 tests/browser/project_workbench_smoke.py。
- 修改 docs/zh/user-guide/web-ui.md。
- 修改 docs/en/user-guide/web-ui.md。
- 修改 README.md 和 README_EN.md（只补充启动、运行状态和限制说明）。

### 后端集成场景

使用 fake core 和临时媒体目录覆盖：

1. 创建三个场景，开始运行，验证 TTS 和图片按场景顺序调用。
2. 第一个场景 TTS 完成后立即观察 duration 和时间线数据，再让图片完成。
3. 第二个场景图片失败，第三个场景仍完成，运行显示 completed_with_failures。
4. 对已有 current image 的场景生成新图片，确认 current 仍不变，candidateReviewCount 为 1。
5. 调用 retry-failed，确认新运行只包含失败场景。
6. 在 TTS 请求期间调用 pause 和 cancel，确认外部请求自然返回，后续场景不会错误启动。
7. 关闭 repository 和服务对象，再用同一 SQLite 初始化并调用 resume_active_runs，确认未完成 item 可继续。
8. 导出时确认使用 current 版本，候选版本只出现在 warning，不改变导出快照。

### 浏览器验收

使用本地 API fake 配置或测试服务器，不调用真实模型。检查：

- 空闲工作台有清晰的“开始生成”入口和待生成计数。
- 生成中显示当前场景、阶段、总进度、暂停和取消。
- 场景列表和时间线逐项变化，页面不跳动。
- 失败列表可点击定位，“仅重试失败项”创建新运行。
- 候选版本不会自动覆盖当前预览，确认后才切换。
- 导出对未确认候选给出警告并保持 current 版本。
- 小屏幕下顶部操作、运行状态、时间线和检查器不互相遮挡。

### 验证命令

    uv run --extra dev pytest tests/integration/test_project_generation_e2e.py tests/api tests/services -q
    Set-Location frontend
    npm run lint
    npm run build
    Set-Location ..
    uv run --extra dev pytest tests/browser/project_workbench_smoke.py -q

启动本地检查时，后端与前端使用未占用端口；例如：

    uv run uvicorn api.app:app --host 127.0.0.1 --port 8001
    Set-Location frontend
    npm run dev -- --host 127.0.0.1 --port 5173

### 里程碑出口与提交

先完成测试、浏览器 smoke 和文档自检，再提交：

    git add tests/integration/test_project_generation_e2e.py tests/browser/project_workbench_smoke.py docs/zh/user-guide/web-ui.md docs/en/user-guide/web-ui.md README.md README_EN.md
    git commit -m "test: verify project generation workbench flow"

## 全量验收清单

- [ ] 现有后端测试通过，除已知 Windows 打包依赖排除和自定义字幕字体 fallback 基线问题外没有新增失败。
- [ ] 新增模型、repository、planner、orchestrator、API 和前端 reducer 测试全部通过。
- [ ] 任意运行状态在 GET 接口中可解释，前端不依赖进程内 TaskManager 才能显示历史结果。
- [ ] 项目重启后 queued/running/paused 运行可恢复，不重复生成 fingerprint 已匹配的素材。
- [ ] 当前图片、候选图片、上传图片和导出快照四者互不覆盖。
- [ ] 旁白变化不触发无意义图片重建；提示词变化不触发音频重建。
- [ ] 所有异步外部调用都有单项错误记录，单项失败不阻塞后续场景。
- [ ] 暂停和取消是协作式语义，文档和界面都没有承诺强杀外部模型请求。
- [ ] 第一版明确关闭项目内并发、SSE/WebSocket、自动重试、多轨时间线和跨项目素材库。
- [ ] 根工作区的用户修改未被回滚、覆盖或混入任何里程碑提交。

## 提交顺序总览

1. test: add project generation fixtures
2. feat: persist project generation runs
3. feat: plan project generation from asset freshness
4. feat: orchestrate sequential project generation
5. feat: expose project generation run API
6. feat: add project generation controls to workbench
7. test: verify project generation workbench flow

每次提交后都要记录本里程碑的测试命令和结果；实现过程中发现需要改变已确认产品规则时，先停在当前里程碑，更新设计规格并等待确认，不直接扩大范围。
