# 快捷创作 P0–P2 生产级优化设计

## 背景与目标

快捷创作已经覆盖文案、分镜、配音、画面、字幕、工作流、提交和历史，但审计确认存在四类生产风险：用户输入未进入最终生成、一个业务任务拥有两个 ID、取消/历史状态不一致、长表单缺少提交保护和移动端布局。目标是在保留现有 React + FastAPI + StandardPipeline 架构的前提下，使流程达到“配置可信、提交可控、状态一致、可恢复、可在窄屏完成”的标准。

## 方案比较

### 方案 A：局部界面修补

只增加确认框、禁用按钮和响应式样式。改动最小，但无法解决逐分镜提示丢失、批量语义和双任务 ID，因此不采用。

### 方案 B：统一任务域模型并渐进重构（采用）

让 API Task ID 成为流水线、输出目录和历史记录的唯一 ID；扩展标准视频请求支持逐分镜输入；前端把单视频与批量视频都转换为同一个 `VideoTaskInput`；在现有工作台上增加阶段导航、草稿恢复、核对摘要、提交锁、取消和响应式抽屉。该方案能够覆盖 P0–P2，同时不重写媒体/TTS/字幕流水线。

### 方案 C：新建队列服务和全新向导

引入数据库、队列 worker、批次表和完全重写的多路由 UI。长期扩展性最好，但超出本轮范围，也会放大迁移和部署风险，因此不采用。

## 后端架构

### 唯一任务身份

`TaskManager.create_task()` 生成的 UUID 是唯一任务 ID。异步视频路由把该 ID 作为内部 `task_id` 参数传入 StandardPipeline；StandardPipeline 使用它创建输出目录并保存 metadata/storyboard。`/api/tasks/{id}`、`/api/history/{id}` 与 `/output/{id}` 始终引用同一实体。

取消流程为：DELETE task → cancel future → LinearPipeline 捕获 `CancelledError` → StandardPipeline 持久化 `cancelled` → TaskManager 标记 `cancelled` → history 返回同一状态。取消是正常终态，不再映射为失败。

### 逐分镜输入

`VideoGenerateRequest` 新增可选 `scenes`：

```json
[{"narration":"旁白","visual_prompt":"画面提示"}]
```

当 scenes 存在时，StandardPipeline 直接使用 narration；非空 visual prompt 进入对应帧，空 prompt 才调用 LLM 补齐。全局 prompt prefix 仍统一应用。旧的 `text + split_mode` 保持兼容。

### 历史列表

历史摘要继续保持轻量，但前端直接读取 `n_frames`。新增/使用详情接口补齐参数和 storyboard，不再从摘要猜测 TTS、工作流、BGM。取消态在类型、筛选、控制台和历史中独立展示。

## 前端数据流

### 单任务与批量任务

快捷创作先生成一个或多个 `VideoTaskInput`：

- AI/手动：一个输入，对应一个视频。
- 批量：每个非空主题生成一个输入，每项只有自己的场景和标题；并发提交，但每项拥有独立任务、取消、失败和重试状态。

批量界面明确显示“将创建 N 个视频”，不再把主题数量描述为分镜数量。

### 提交安全

提交前展示核对区：标题/视频数/分镜数、TTS、工作流、画布尺寸、字幕、BGM、预计旁白时长。核对区包含确认复选框。提交期间 CTA 锁定并显示状态；同一次提交使用稳定 client request key，防止双击重复创建。

### 工作台流程

采用五阶段模型：内容、分镜、声音与画面、核对并生成、进度与结果。前四阶段在快捷创作页用阶段导航和锚点表达，当前阶段、完成度和错误数可见；第五阶段由可收起任务抽屉与历史页承载。保留用户熟悉的现有配置卡，避免大规模视觉重写。

### 草稿与预设

标题、模式、主题、文案、分镜、批量输入和关键输出设置保存到版本化 localStorage 草稿。重新打开时恢复，成功提交后保留配置但记录最近提交时间。预设载入先通过共享规范化函数校验，字幕值不会在 API 边界静默变化；非法值在 UI 中立即规范化并给出说明。

### 错误处理

所有 API 请求复用公开的 `requestJson()` 与 `formatApiErrorValue()`。Toast、任务 errorMsg 和可展开技术详情只接收字符串。FastAPI `detail[]` 显示为字段路径加消息，未知对象使用安全 JSON 文本，绝不显示 `[object Object]`。

## 响应式与可访问性

- 小于 `lg`：侧栏默认隐藏，通过头部菜单打开；Console 变为右侧抽屉；主创作区占满宽度。
- `lg` 以上：保留桌面三栏，但 Console 可折叠。
- Tab 切换时主内容滚动归零。
- 所有新控件具备可访问名称、键盘焦点、`aria-current`/`aria-expanded`/`aria-live`；删除、取消不依赖 hover。
- 状态来自真实 `serviceStatus` 和当前 provider/model；不再硬编码绿色 Ready。暂不实现完整英文翻译，移除无效语言开关，避免虚假能力。

## 测试策略

1. 后端：scene schema/转发、固定场景 prompt、统一任务 ID、取消持久化、TaskManager 取消终态。
2. 前端 API：错误对象格式化、scene payload、history 摘要、cancelled 状态、字幕规范化。
3. 前端行为契约：批量一主题一任务、提交锁/确认、草稿恢复、取消按钮、真实状态标签、响应式类和滚动复位。
4. 回归：完整 pytest、TypeScript、Node tests、Vite build、Compose config。
5. 浏览器：桌面与 390px 窄屏验证，不触发付费生成；用请求拦截或只读页面状态验证提交摘要与布局。

## 明确不做

- 不引入 Redis/Celery/数据库队列。
- 不实现完整多语言翻译系统。
- 不把试听音频或测试图直接注入成片；本轮先明确“仅预览”，避免误导。
- 不重写现有模板、字幕渲染、TTS 或媒体供应商实现。

