# 引导式分镜导演台设计

## 目标

让分镜数量默认由系统根据旁白语义、信息密度和口播节奏自动决定，同时保留用户对节奏和固定数量的控制。生成结果必须让旁白、画面、必要文字锚点和视觉风格保持一致，并且不能覆盖用户已经确认或修改的内容。

本期采用“引导式导演台”方案：自动导演、节奏倾向、软目标数量、语义分析、分镜列表、字段级锁定和分离的重新生成动作集中在现有内容步骤中完成。

## 非目标

- 本期不引入可拖拽的多轨时间线。
- 本期不建立复杂的镜头语言模板库或镜头运动编辑器。
- 本期不替用户强制指定画风；画风前缀仍由用户填写。
- 本期不改变已有手工分镜的默认边界。

## 用户体验

### 默认入口

导演台默认状态为：

```ts
directorMode: "auto"
density: "standard"
targetSceneCount: null
```

界面保留四种互斥选择：

1. 自动导演 · 稀疏
2. 自动导演 · 标准（默认）
3. 自动导演 · 密集
4. 自定义固定数量

自动模式由 LLM 决定实际镜头数。稀疏、标准、密集只表达节奏倾向，不把镜头数硬编码为固定值。自定义模式显示数量输入框，数量是软目标而不是字符切分命令。

### 生成后状态

点击“生成分镜旁白”后，系统自动完成语义分析、旁白单元生成、视觉锚点提取和画面提示词生成，然后直接进入分镜列表，不因数量偏差阻断流程。

列表顶部显示：

- 当前节奏模式。
- 实际镜头数和预计总时长。
- 自定义模式下的目标数量（如果有）。
- 数量差异提醒及原因。

示例：`目标 6 个，实际采用 4 个自然语义镜头；文案只有 4 个独立语义段，已避免生硬切分。`

### 分镜卡片

每个镜头显示并可编辑：

- 旁白原文。
- 预计口播时长。
- 语义焦点 `visualFocus`。
- 必须体现的文字或数字 `textAnchors`。
- 画面提示词。
- 锁定状态和人工编辑标记。

用户修改某个字段后，该字段自动标记为人工编辑；后续重新生成不得覆盖该字段。用户也可以显式锁定整镜头。

### 重新生成动作

- **重新生成分镜旁白**：重新计算语义边界、镜头数、时长和旁白单元；保留用户编辑或锁定的字段。
- **仅重新生成画面**：保留旁白、镜头边界和时长，只更新视觉提示词；保留锁定的画面字段。
- **生成未锁定镜头**：跳过锁定镜头，并跳过已人工编辑的字段。
- **重新分析**：只更新数量建议、语义焦点、文字锚点和警告，不直接改变用户已经编辑的旁白。

## 状态与数据契约

### 导演配置

```ts
type DirectorMode = "auto" | "custom";
type StoryboardDensity = "sparse" | "standard" | "dense";

interface StoryboardDirectorConfig {
  directorMode: DirectorMode;
  density: StoryboardDensity;
  targetSceneCount: number | null;
}
```

兼容层继续接受已有的 `splitType`、`sceneCount` 和手工 `scenes`。没有新字段的旧项目映射为 `auto + standard`；明确的旧固定数量映射到 `custom`，但仍使用自然边界和接近数量提醒规则。

### 分析结果

```ts
interface StoryboardAnalysis {
  recommendedSceneCount: number;
  actualSceneCount: number;
  targetSceneCount: number | null;
  density: StoryboardDensity;
  estimatedDurationSeconds: number;
  semanticUnits: Array<{
    narration: string;
    reason: string;
    visualFocus: string;
    textAnchors: string[];
    estimatedDurationSeconds: number;
  }>;
  warnings: string[];
}
```

### 镜头编辑状态

```ts
interface StoryboardFieldState {
  lockedFields: Array<"narration" | "visualPrompt" | "visualFocus" | "textAnchors">;
  editedFields: Array<"narration" | "visualPrompt" | "visualFocus" | "textAnchors">;
  locked: boolean;
}
```

## 生成流程

1. 前端提交旁白、导演模式、节奏倾向和可选目标数量。
2. 后端调用 `POST /api/storyboard/analyze` 完成语义分析。
3. 自动模式由 LLM 选择合理镜头数；节奏倾向作为目标字数、镜头变化频率和平均停留时长的提示。
4. 自定义模式尝试满足目标数量，但只允许在自然语义边界拆分或合并。
5. 校验所有旁白单元拼接后与原文完全一致；失败时拒绝该次 LLM 切分并使用安全降级。
6. 如果目标数量无法自然满足，选择距离最近的合理数量；距离相同优先较少镜头，避免过度切碎。
7. 生成视觉焦点、关键文字锚点、预计时长和画面提示词。
8. 返回分析结果、镜头列表和非阻断提醒，前端直接进入列表。

## 后端接口

### 分析请求

```json
{
  "narration": "原始旁白文本",
  "director_mode": "auto",
  "density": "standard",
  "target_scene_count": null
}
```

### 分析响应

```json
{
  "recommended_scene_count": 4,
  "actual_scene_count": 4,
  "target_scene_count": 6,
  "density": "standard",
  "estimated_duration_seconds": 37,
  "semantic_units": [],
  "warnings": ["目标 6 个，实际采用 4 个自然语义镜头"]
}
```

项目创建和标准生成管线保存导演配置与分析快照。生图提示词生成只消费旁白、`visualFocus`、`textAnchors` 和用户填写的 `promptPrefix`，不把视觉焦点或锚点混入 TTS 文本。

## LLM 约束

语义切分提示词要求：

- 只输出严格 JSON。
- 不改写、总结、翻译或补充原文。
- 拼接所有 `narration` 必须与输入原文完全一致。
- 不在中文词语、英文单词、日期、小数、版本号中间切分。
- 优先句末边界，再使用逗号、分号、冒号等明确停顿。
- 每个单元只声明一个主要语义焦点。
- 抽取星期、日期、时间、数字、地点、名称、动作和可视化隐喻。

画面提示词约束：

- 关键文字只在语义必要时出现，并放置在日历、钟表、票据、地图、清单、表格、书页或界面等合理载体上。
- 长文本不强行生成到画面中，改为预留后期字幕或叠字区域。
- 用户的 `promptPrefix` 作为整段序列的风格锁定；为空时不擅自添加媒介、色彩、时代或镜头风格。
- 相邻镜头轮换景别和构图，同时保持主体、服装色块和关键道具连续。

## 错误与降级

- LLM 不可用或返回非法 JSON：使用本地语义切分和已有安全规则。
- LLM 切分无法还原原文：丢弃该结果，不污染旁白，返回安全结果和警告。
- 语义单元不足：采用最近合理数量并显示非阻断提醒。
- 有手工画面提示词的旧场景：不自动改变其边界。
- 分析接口失败：保留本地即时分析，允许用户继续生成。

## 实现边界

前端重点修改 Quick Create 内容步骤、导演配置状态、分镜列表卡片、提醒条和重新生成动作；类型定义与草稿/预设持久化同步新字段。后端重点修改分析请求模型、项目配置归一化、项目创建和标准管线参数传递。LLM 提示词保持严格 JSON 和原文完整性约束。

## 验收与测试

### 前端

- 初始状态为自动标准，数量输入框默认隐藏。
- 四种模式互斥，切换自定义时才启用数量输入。
- 自动模式展示推荐数量、实际数量和预计时长。
- 数量不一致时直接进入列表并显示提醒。
- 单镜头锁定和字段级人工编辑标记可见且有效。
- 三种重新生成动作不会越过锁定或人工编辑字段。

### 后端与提示词

- 稀疏、标准、密集产生可验证的节奏差异。
- 自定义目标无法满足时返回最近数量和原因。
- 分割后拼接文本与原文严格一致。
- 日期、小数和版本号不会被错误切断。
- 视觉焦点和文字锚点传递到生图提示词，但不进入旁白或字幕文本。
- 旧项目和旧预设仍能正常加载、生成和复用。

### 回归

运行现有 Python 测试、前端 TypeScript 测试、lint、build 和 compileall；补充导演配置、软目标数量、锁定保护和接口响应的专项测试。

## 分阶段交付

1. 数据模型、接口和 LLM 契约。
2. Quick Create 导演台和分析结果展示。
3. 分镜列表锁定、人工编辑保护和分离生成动作。
4. 兼容旧配置、补充测试、完成构建和端到端冒烟。
