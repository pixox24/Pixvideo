# 视觉提示词导演系统优化归档

> 归档目的：记录本轮“故事/旁白 → 自动分镜画面提示词 → 图像生成”链路的设计决策、代码改动、兼容边界和验证结果，便于后续追溯、回归和继续演进。
>
> 适用范围：PixVideo 工作台自动分镜、标准视频管线、项目创建时的画面提示词补全，以及 LLM 调用层。

---

## 1. 本轮优化结论

本轮优化解决了两个层面的问题：

1. **创意质量问题**：旧提示词只要求“场景 + 动作 + 情绪 + 象征元素”，模型容易生成普通的角色摆拍、温馨室内场景或泛化的影视截图。
2. **工程链路问题**：新的视觉规则曾经只存在于对话文本中，没有进入真实 LLM 请求；空提示词还会被旁白回填，导致自动补全失效；旧项目中的提示词会被持久化并继续复用。

现在的处理方式是：

```text
用户旁白
  ↓
视觉导演 system prompt
  + 当前批次旁白 user prompt
  ↓
严格 JSON image_prompts 数组
  ↓
项目中的 visual_prompt（语义基础提示词）
  ↓
图像 API 边界拼接 promptPrefix
  ↓
最终图像生成提示词
```

核心原则：

- **系统规则和旁白内容分离**；
- **模型负责画面语义，项目配置负责最终风格前缀**；
- **空提示词保持为空，不再使用旁白冒充画面提示词**；
- **用户手工编辑的非空提示词默认不被覆盖**；
- **旧旁白污染值可以被识别并重新生成**。

---

## 2. 优化前的问题

### 2.1 规则没有进入真实请求

旧版代码将全部规则拼接到一个 user prompt 中。此前设计文档中虽然已经提出了“视觉导演规则集”，但它没有真正写入 `image_generation.py`，也没有通过 `system` 角色发送给模型。

`LLMService` 原先主要发送：

```python
messages=[{"role": "user", "content": prompt}]
```

因此，“已经升级了系统提示词”并不等于运行中的模型真的收到了升级后的规则。

### 2.2 旧规则过于宽泛

旧规则重点要求：

- scene；
- character action；
- emotion；
- symbolic elements；
- 50–100 个英文单词。

这类约束可以生成合格的英文图片描述，但无法稳定控制：

- 构图是否有冲击力；
- 镜头之间是否统一；
- 是否出现普通人物摆拍；
- 是否有明确光源和阴影；
- 是否使用有限色彩；
- 是否把抽象概念转成视觉隐喻；
- 是否出现文字、字幕、Logo 或水印。

因此类似下面的结果是旧规则下的合理产物，而不是模型“没有听新规则”：

```text
A mother gently placing a small key into the open palm of her young daughter...
```

### 2.3 旁白污染视觉提示词

前端曾经存在以下回退逻辑：

```tsx
visualPrompt: scene.visualPrompt.trim() || scene.ttsText
```

当用户没有手动填写画面提示词时，旁白会被写入 `visualPrompt`。后端随后认为该场景已经拥有提示词，自动 LLM 补全不会执行。

### 2.4 旧项目会继续复用历史提示词

项目、任务和生成运行都会持久化 `visual_prompt`。普通重新生成图片只会使用已经保存的提示词，不会重新调用 LLM 设计分镜。

因此：

- 重启服务不会改变已经保存的字符串；
- 重新生成图片不会自动重新生成画面提示词；
- 旧项目中的 `A mother...` 仍然可能继续被使用；
- 必须新建项目、清空提示词，或增加显式的“重新设计画面提示词”动作。

---

## 3. 新的视觉导演规则

实际规则位于：

```text
pixelle_video/prompts/image_generation.py
```

常量：

```python
IMAGE_PROMPT_GENERATION_SYSTEM_PROMPT
```

### 3.1 单一视觉主张

每个镜头必须先确定一个主导视觉主张：

- 一个视觉隐喻；
- 一个关键道具；
- 一个空间关系；
- 一个光影关系；
- 或一个决定情绪的动作瞬间。

禁止把多个无关象征物堆在同一个镜头里。

错误方向：

```text
母亲、钥匙、书架、花园、高跟鞋、束腰、门、很多钥匙全部同时出现。
```

正确方向：

```text
让“选择权”由一个巨大的、被光切开的门缝表达；人物只作为门缝边缘的微小剪影存在。
```

### 3.2 非普通构图

每个镜头至少使用一种明确构图策略：

- 主体边置；
- 大面积负空间；
- 前景遮挡；
- 对角线透视；
- 极端俯视或仰视；
- 局部特写；
- 镜面或倒影；
- 门框、窗框、栏杆、树影切割画面；
- 尺度失衡；
- 超长投影替代人物本体。

默认禁止：

- 人物居中站立；
- 面向镜头的证件式构图；
- 普通“人物在房间里做动作”；
- 平均布光；
- 无主次的背景素材堆积。

### 3.3 统一视觉世界

同一组分镜必须共享：

- 统一的绘画媒介或材质；
- 相近的光影逻辑；
- 受控的色彩体系；
- 一致的空间气质；
- 一致的叙事密度。

镜头可以轮换景别和构图，但不能每一镜换一种完全不同的画风。

### 3.4 受控色彩

每个镜头必须使用 2–4 个主色，并明确主色关系。

可用方向包括：

- 孤独/夜晚：深靛蓝、青蓝、黑色、少量暖窗光；
- 冲突/危险：珊瑚红、酒红、青绿、黑色；
- 梦境/异化：紫色、薰衣草色、黑色、少量亮粉；
- 警觉/焦虑：酸性黄绿、黑色、锈红；
- 温柔/怀旧：奶油黄、灰蓝、珊瑚粉、深墨蓝；
- 黑色电影：黑色、白色高光、单一强调色。

禁止彩虹霓虹、平均照明和无主色画面。

### 3.5 光影与材质

每条 prompt 必须具体写出：

- 光源来自哪里；
- 光线如何切割空间；
- 阴影是否硬边；
- 哪一个区域被隐藏；
- 使用什么统一材质。

允许的材质语言：

- 纸张颗粒；
- 丝网印刷颗粒；
- 墨线；
- 干刷纹理；
- 网点；
- 平面色块；
- 硬边海报印刷质感。

### 3.6 镜头序列节奏

相邻镜头不应连续使用相同景别或同一种构图。

优先使用以下节奏：

```text
环境建立远景
→ 人物被空间吞没的中远景
→ 道具/肢体局部特写
→ 非直译的心理过场
→ 具有张力的低角度、顶视或窥视镜头
```

每 4–6 个镜头至少有一个非直译镜头，例如：

- 空椅子；
- 破碎倒影；
- 门缝；
- 雨水中的倒影；
- 植物投影；
- 远处的影子；
- 被光切断的物件；
- 没有角色但能表达心理状态的房间。

### 3.7 文字和污染控制

图像模型提示词明确禁止：

- subtitles；
- captions；
- readable text；
- letters；
- numbers；
- signage；
- UI；
- logos；
- brand marks；
- watermarks。

旁白仍然用于 TTS 和后期字幕，不得作为画面中的文字内容传给图像模型。

---

## 4. 系统提示词与 user prompt 的职责分离

### 4.1 system prompt 负责什么

`IMAGE_PROMPT_GENERATION_SYSTEM_PROMPT` 负责不可被旁白改变的规则：

- 角色定位；
- 视觉媒介；
- 构图要求；
- 色彩要求；
- 光影要求；
- 风格统一；
- 禁止项；
- JSON 输出契约。

### 4.2 user prompt 负责什么

`build_image_prompt_prompt()` 只负责当前请求的数据：

- 当前批次的旁白；
- 当前批次序号；
- 总批次数；
- 已完成数量；
- 输出数量；
- 英文单词数范围；
- JSON 形状。

user prompt 不再重复整套视觉导演规则，也不注入上一批已经生成的 prompt，避免跨批次提示词泄漏。

### 4.3 风格前缀的职责

前端的 `promptPrefix` 是用户选择的风格参考，不是场景主体。

它会被绑定到 system prompt 中，告诉模型：

```text
这是视觉媒介、调色和时代感约束，不是需要画进画面的物件，也不是可读文字。
```

在实际图像 API 边界，已有的 `build_image_prompt()` 仍负责最终拼接：

```text
promptPrefix + ", " + visual_prompt
```

这样避免：

- LLM 输出中重复加入风格前缀；
- 图像 API 再次重复加入风格前缀；
- 用户自定义风格与模型默认风格发生无规则竞争。

---

## 5. 代码改动清单

### 5.1 `pixelle_video/prompts/image_generation.py`

改动：

- 新增 `IMAGE_PROMPT_GENERATION_SYSTEM_PROMPT`；
- 将原始长模板缩减为 user-side 输入和输出契约；
- 新增 `build_image_prompt_system_prompt(style_prefix)`；
- 保留 `build_image_prompt_prompt()` 和 `image_prompts` 数组格式，保证兼容已有调用方；
- 加入批次元数据，但不传递上一批实际 prompt 内容。

### 5.2 `pixelle_video/prompts/__init__.py`

导出：

```python
IMAGE_PROMPT_GENERATION_SYSTEM_PROMPT
build_image_prompt_system_prompt
```

确保生成器只从统一 prompts 包获取规则，避免出现多个隐藏版本。

### 5.3 `pixelle_video/services/llm_service.py`

新增：

```python
system_prompt: Optional[str] = None
```

标准输出和结构化输出都会构造：

```python
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": prompt},
]
```

如果没有传 system prompt，则保留历史单 user message 行为。

### 5.4 `pixelle_video/utils/content_generators.py`

改动：

- `generate_image_prompts()` 使用真实 system message；
- 支持 `style_prefix`；
- 保留批量生成和重试机制；
- 严格校验 `image_prompts` 是非空字符串数组；
- 数量不匹配、空响应、非法 JSON 会触发重试或抛出明确错误；
- 不接受字典、空值或混合类型作为有效结果。

### 5.5 `api/routers/workbench.py`

`GenerateScriptRequest` 新增可选：

```python
promptPrefix: str | None = None
```

`/api/generate-script` 将前端风格前缀传递给图像提示词生成器。

### 5.6 `frontend/src/components/QuickCreate.tsx`

改动：

```tsx
visualPrompt: scene.visualPrompt.trim()
```

删除旁白回退，确保空视觉提示词仍然为空。

自动分镜请求也会传递当前 `promptPrefix`。

### 5.7 `api/routers/projects.py`

改动：

- 新项目创建时识别 `visual_prompt == narration` 的历史污染值；
- 清除污染后触发 LLM 自动生成；
- LLM 未配置或失败时保留空值；
- 不再把旁白写入 `visual_prompt`；
- 自动补全支持当前项目的风格前缀；
- 保留用户真实编辑过的非空 prompt。

### 5.8 `pixelle_video/pipelines/standard.py`

改动：

- 标准管线识别旁白污染值；
- 对真正缺失的提示词调用新视觉导演生成器；
- 将风格前缀传入 system prompt；
- 普通生成仍然复用真实用户提示词，不做无条件覆盖；
- 最终 provider prompt 仍通过既有前缀拼接逻辑生成。

### 5.9 `pixelle_video/utils/prompt_helper.py`

新增通用工具：

```python
normalize_prompt_text()
is_visual_prompt_same_as_narration()
```

其中 `is_visual_prompt_same_as_narration()` 用于识别旧版 `visualPrompt || ttsText` 造成的污染。

---

## 6. 数据状态和兼容策略

### 6.1 场景字段定义

| 字段 | 含义 |
| --- | --- |
| `narration` | TTS 和字幕使用的旁白文本 |
| `visual_prompt` | LLM 生成或用户编辑的语义画面提示词 |
| `promptPrefix` | 用户选择的统一风格前缀 |
| provider prompt | 发送图像 API 前拼接完成的最终提示词 |

### 6.2 默认不覆盖用户编辑

以下情况不会被普通生成流程覆盖：

- `visual_prompt` 非空；
- `visual_prompt` 与旁白不同；
- 用户在工作台里手工修改过画面提示词。

### 6.3 旧项目如何使用新规则

已有项目中的旧 prompt 不会因为重启自动改变，这是有意设计，用于保护用户编辑结果。

重新使用新规则的方法：

1. 新建项目并重新生成自动分镜；
2. 在工作台清空需要更新的画面提示词；
3. 重新执行画面提示词生成动作；
4. 如果后续扩展“全部重新设计提示词”按钮，应使用显式 force 参数，不改变默认复用语义。

注意：点击“重新生成图片”只会重新使用当前 prompt，不等同于重新调用 LLM。

---

## 7. 失败处理策略

### 7.1 LLM 未配置

行为：

- 记录 warning；
- `visual_prompt` 保持空值；
- 不将旁白写入提示词；
- 后续生成运行仍可识别该场景为待补全状态。

### 7.2 LLM 返回非法 JSON

行为：

- 清理完整 JSON Markdown fence；
- 校验对象、数组、字符串和数量；
- 失败时按照重试次数重试；
- 最终失败抛出明确异常，避免静默保存错误数据。

### 7.3 LLM 返回旁白作为 prompt

如果生成结果与对应旁白完全相同，则该结果不会写入 `visual_prompt`，场景保持为空并记录失败原因。

### 7.4 生成批次失败

每个批次独立重试。批次上下文只包含：

- 批次序号；
- 总批次数；
- 已完成数量；
- 当前批次旁白。

不把之前生成的 prompt 放进后续 user prompt，避免出现“上一镜的母亲、钥匙、书架”污染下一镜。

---

## 8. 验证记录

本轮已执行：

```bash
python -m compileall -q api pixelle_video tests/utils/test_image_prompt_generation.py
```

结果：通过。

```bash
python -m pytest tests/utils/test_image_prompt_generation.py tests/api/test_projects.py tests/pipelines/test_standard_composition_config.py
```

结果：

```text
20 passed
```

另外已执行：

```bash
python -m pytest tests/utils/test_image_prompt_generation.py tests/utils/test_narration_batching.py
```

结果：

```text
13 passed
```

项目与生成规划相关测试结果：

```text
28 passed
```

前端检查：

```bash
cd frontend
npm run lint
npm run build
```

结果：

- TypeScript 检查通过；
- Vite 构建通过；
- 仅存在已有的 bundle 体积提示，没有新增构建错误。

测试文件：

```text
tests/utils/test_image_prompt_generation.py
```

覆盖内容：

- system/user prompt 分离；
- system message 角色验证；
- 标准和结构化 LLM 调用；
- 严格 JSON 响应验证；
- 风格前缀作为 style lock；
- 旁白污染识别；
- 自动补全失败时保持空值；
- 批次之间不泄漏上一批 prompt。

---

## 9. 运维和排查步骤

### 9.1 修改提示词模板后

必须重启后端进程，因为 Python 模块中的提示词常量在进程启动时加载。

### 9.2 验证新系统提示词是否生效

建议检查日志中是否进入：

```text
Generating image prompts
Processing image prompt batch
```

并确认实际 LLM 请求同时包含：

```text
role=system
role=user
```

### 9.3 仍然出现旧版母亲/钥匙提示词

按以下顺序排查：

1. 是否正在打开旧项目；
2. 当前场景的 `visual_prompt` 是否已经持久化；
3. 是否只是点击了“重新生成图片”，而不是重新生成画面提示词；
4. 是否前端仍然运行旧 bundle；
5. 后端服务是否已经重启；
6. 是否将旁白复制到了视觉提示词输入框。

### 9.4 仍然出现字幕或可读文字

这属于图像模型执行层问题，不是 TTS 字幕层问题。确认：

- 图像 prompt 中包含 `no readable text, no captions, no watermark`；
- 旁白没有被拼接进 `visual_prompt`；
- 后期字幕是否由独立字幕渲染器生成；
- 当前图像是否是旧版本缓存或旧资产。

---

## 10. 已知边界与后续建议

### 当前边界

1. `image_prompts` 仍是字符串数组，暂未把 `visual_metaphor`、`composition`、`lighting_and_palette` 作为独立数据库字段保存。
2. 普通生成流程不会自动覆盖旧项目提示词。
3. 工作台中的 `visual_prompt` 是语义基础提示词；最终 provider prompt 还会在图像生成边界拼接 `promptPrefix`。
4. 新规则可以显著提高风格一致性，但图像模型本身仍可能偶尔违反文字禁用或构图要求，需要通过结果审核和重新生成处理。

### 推荐后续迭代

1. 增加“重新设计全部画面提示词”按钮；
2. 增加显式 `forceVisualPromptRefresh` 参数；
3. 将结构化导演中间结果保存为版本快照：

```json
{
  "visualMetaphor": "...",
  "composition": "...",
  "lightingAndPalette": "...",
  "imagePrompt": "...",
  "negativePrompt": "..."
}
```

4. 在工作台同时显示：
   - 语义基础提示词；
   - 风格前缀；
   - 最终发送给图像 API 的完整 prompt；
5. 增加 prompt 质量检查器，自动检测：
   - 是否包含字幕/文字词汇；
   - 是否缺少光源；
   - 是否缺少调色盘；
   - 是否出现居中人物摆拍；
   - 是否与旁白完全相同；
6. 为不同项目保存视觉 Bible，避免同一项目在多次补生成时发生材质漂移。

---

## 11. 变更文件索引

本轮相关文件：

```text
api/routers/projects.py
api/routers/workbench.py
frontend/src/components/QuickCreate.tsx
pixelle_video/pipelines/standard.py
pixelle_video/prompts/__init__.py
pixelle_video/prompts/image_generation.py
pixelle_video/services/llm_service.py
pixelle_video/utils/content_generators.py
pixelle_video/utils/prompt_helper.py
tests/utils/test_image_prompt_generation.py
```

本归档文档只记录设计、实现和验证事实，不代表已经创建 Git commit。