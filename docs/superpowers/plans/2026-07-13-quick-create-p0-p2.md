# 快捷创作 P0–P2 一次性优化实施计划

**状态：** 已完成实现与全量回归

**设计依据：** `docs/superpowers/specs/2026-07-13-quick-create-p0-p2-design.md`

**目标：** 在不引入数据库、Redis、Celery 或重写媒体流水线的前提下，让快捷创作从内容录入、分镜、生产设置、提交、进度到历史记录形成可信、可取消、可恢复、可在移动端完成的闭环。

## 实施边界

- 保留 React 19 + FastAPI + `TaskManager` + `StandardPipeline`。
- API 任务 UUID 同时作为流水线、输出目录和历史记录 ID。
- 不调用付费 LLM、TTS、图片或视频生成完成验收；浏览器测试使用只读状态和提交前交互。
- 不自动修改或删除改造前已经产生的孤立历史数据；新任务全部使用统一 ID。

## P0：生产正确性与提交安全

### P0-1 逐分镜数据进入最终流水线

**修改文件**

- `api/schemas/video.py`
- `api/routers/video.py`
- `pixelle_video/pipelines/standard.py`
- `frontend/src/lib/api.ts`

**代码修改**

- [x] 请求模型增加 `scenes[{narration, visual_prompt}]`，限制 1–30 项并拒绝空白旁白。
- [x] 前端把每个分镜的旁白和画面提示词原样序列化到 API。
- [x] 标准流水线存在显式 scenes 时跳过再次切文案。
- [x] 非空画面提示词直接使用，仅为空的分镜调用 LLM 补全，再统一应用 prompt prefix。
- [x] 全文案模式按用户选择的段落、行或句子规则切分后再均衡到目标分镜数。

**回归测试**

- `tests/api/test_video_scenes.py`
- `frontend/src/lib/api.test.ts`
- `tests/frontend/test_quick_create_workflow.py`

### P0-2 统一任务 ID、取消终态和幂等提交

**修改文件**

- `api/routers/video.py`
- `api/routers/tasks.py`
- `api/tasks/manager.py`
- `pixelle_video/pipelines/linear.py`
- `pixelle_video/pipelines/standard.py`
- `frontend/src/App.tsx`
- `frontend/src/types.ts`

**代码修改**

- [x] 把 API UUID 注入 `StandardPipeline`，输出目录、metadata、storyboard、任务查询和历史记录共用同一 ID。
- [x] `TaskManager.cancel_task()` 改为异步等待协作取消完成。
- [x] 捕获 `CancelledError`，把 `cancelled` 持久化为独立终态，不再误报为 failed。
- [x] 控制台与历史记录都提供运行中任务取消入口。
- [x] 提交阶段点击取消会记录取消意图，后端 ID 返回后立即执行真实取消；运行中任务必须先取消，不能直接删除输出目录。
- [x] 前端每次提交生成稳定 client request key；后端同 key 复用任务并忽略重复启动。
- [x] 并发批量提交的本地临时任务使用随机 UUID，避免毫秒时间戳碰撞。

**回归测试**

- `tests/api/test_video_task_identity.py`
- `tests/frontend/test_pending_task_ids.py`
- `frontend/src/lib/api.test.ts`

### P0-3 错误、字幕和历史数据可信

**修改文件**

- `frontend/src/lib/api.ts`
- `frontend/src/App.tsx`
- `frontend/src/components/QuickCreate.tsx`
- `api/routers/workbench.py`
- `api/routers/history.py`

**代码修改**

- [x] 统一格式化 FastAPI 的字符串、对象和数组错误，字段校验显示为“路径：消息”。
- [x] Toast 边界接受 unknown 并转成安全字符串，所有直接 `fetch` 的 `Error` 构造也先格式化，消除 `[object Object]`。
- [x] 字幕值在前端提交和后端预设存储边界同时规范化。
- [x] 历史分镜数读取 `n_frames`，配置摘要读取持久化 input，不再使用伪默认值。
- [x] 历史详情并行补充；单条旧记录损坏时保留摘要并降级，不影响整个列表。

**回归测试**

- `tests/frontend/test_error_serialization.py`
- `tests/frontend/test_history_state.py`
- `tests/api/test_history_summary.py`
- `tests/api/test_workbench_presets.py`
- `tests/frontend/test_llm_settings_flow.py`

### P0-4 批量语义和提交确认

**修改文件**

- `frontend/src/components/QuickCreate.tsx`
- `frontend/src/App.tsx`

**代码修改**

- [x] 批量模式一行一个主题，每项形成独立的一分镜视频任务。
- [x] 批量并发上限固定为 3，每项拥有独立任务 ID、状态、取消和重试能力。
- [x] 批量提交准确显示成功与失败数量，不会在部分提交失败时误报全部成功。
- [x] 提交前展示视频数、分镜数、TTS、工作流、画布、字幕、BGM 和预计旁白时长。
- [x] 必须勾选核对确认；提交时同步锁定点击和按钮 loading。
- [x] 用户确认后只要修改任何生产参数，确认立即失效，必须重新核对。

**回归测试**

- `tests/frontend/test_quick_create_batch.py`
- `tests/frontend/test_quick_create_workflow.py`
- `tests/browser/quick_create_smoke.py`

## P1：流程清晰、可恢复、状态一致

### P1-1 五阶段工作流

**修改文件**

- `frontend/src/components/QuickCreate.tsx`
- `frontend/src/App.tsx`

**代码修改**

- [x] 增加“内容、分镜、声音与画面、核对并生成、进度与结果”五阶段导航。
- [x] 前四阶段关联页面锚点、当前阶段和完成标记；第五阶段引导到任务面板/历史。
- [x] Tab 切换后主内容滚动归零，避免进入新页面时停留在旧滚动位置。

### P1-2 版本化草稿恢复

**修改文件**

- `frontend/src/components/QuickCreate.tsx`

**代码修改**

- [x] 使用 `pixvideo.quick-create.draft.v1`，编辑后 500ms 自动保存并显示保存时间。
- [x] 恢复标题、模式、主题、文案、分镜、批量输入和全部关键生产设置。
- [x] 验证恢复的 scenes 结构，损坏 JSON 自动清除，异常字段回退默认值。
- [x] 恢复批量输入时重新计算可见主题数。
- [x] 首次加载时已恢复的草稿优先于自动选择的初始预设；之后用户主动切换预设仍正常生效。

### P1-3 真实预览与历史状态

**修改文件**

- `frontend/src/components/QuickCreate.tsx`
- `frontend/src/components/ConsolePanel.tsx`
- `frontend/src/components/HistoryList.tsx`
- `frontend/src/lib/api.ts`

**代码修改**

- [x] TTS 试听、当前文案合成和测试图明确标注“仅供预览，不会复用到最终成片”。
- [x] `completed`、`failed`、`cancelled` 分别显示，不混用失败样式和文案。
- [x] 历史刷新按统一 ID 对账，不让旧的乐观状态覆盖持久化终态。

**回归测试**

- `tests/frontend/test_quick_create_workflow.py`
- `tests/frontend/test_history_state.py`
- `tests/browser/quick_create_smoke.py`

## P2：响应式、可访问性和真实系统状态

### P2-1 响应式工作台

**修改文件**

- `frontend/src/App.tsx`
- `frontend/src/components/ConsolePanel.tsx`

**代码修改**

- [x] 小屏侧栏改为遮罩抽屉，任务面板改为右侧全高抽屉，主工作区占满可用宽度。
- [x] 桌面任务面板支持收起，390px 视口仍能进入并完成主创作流程。

### P2-2 可访问性和能力诚实

**修改文件**

- `frontend/src/App.tsx`
- `frontend/src/components/QuickCreate.tsx`
- `frontend/src/components/HistoryList.tsx`
- `frontend/src/index.css`

**代码修改**

- [x] 移除没有完整翻译能力的假语言切换。
- [x] LLM、BizyAir、MiniMax 状态来自真实配置和 service status，不再硬编码 Ready。
- [x] 新控件增加关联 label、`aria-label`、`aria-current`、`aria-expanded` 和 `aria-live`。
- [x] 删除/取消操作不依赖 hover；全局增加清晰的 `:focus-visible`。

**回归测试**

- `tests/frontend/test_quick_create_responsive_accessibility.py`
- `tests/browser/quick_create_smoke.py`

## 文档同步

**修改文件**

- `README.md`
- `README_EN.md`
- `docs/zh/user-guide/web-ui.md`
- `docs/en/user-guide/web-ui.md`

**完成项**

- [x] 中英文说明五阶段流程、真实批量语义、提交核对、草稿恢复、取消状态和预览资产边界。

## 最终回归记录

- [x] `uv run --extra dev pytest -q`：186 passed，12 个既有 Pydantic 弃用警告。
- [x] `uv run --extra dev ruff check api pixelle_video tests`：通过。
- [x] `cd frontend && npm run lint`：TypeScript `tsc --noEmit` 通过。
- [x] `cd frontend && npx tsx --test src/lib/*.test.ts`：10 passed。
- [x] `cd frontend && npm run build`：通过；JS 376.82 KB raw / 104.53 KB gzip。
- [x] `docker compose config --quiet`：通过。
- [x] 无付费调用的桌面与 390px 浏览器 smoke test：通过；阶段导航、草稿恢复、批量核对、CTA 锁、移动导航和任务抽屉均验证。
- [x] `git diff --check` 与最终差异范围审计：通过。

## 已知兼容说明

- 改造前可能存在“异步 UUID 已取消，但旧时间戳历史 ID 仍显示 running”的孤立记录。它不具备可靠的一一映射依据，因此本轮不猜测、不删除用户历史数据。
- 改造后的所有新任务均使用统一 UUID，不再产生新的双 ID 记录。
- 现有 Pydantic class-based `Config` 弃用警告属于仓库既有技术债，不影响本轮行为；可在后续独立迁移到 `ConfigDict`。
