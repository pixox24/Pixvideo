# 参考图画风卡槽与阿里百炼视觉理解接入方案

> 状态：可执行开发规格
>
> 版本：v1.0
>
> 更新时间：2026-08-19

## 1. 目标与边界

用户上传一张参考图，系统调用多模态模型提取可迁移的视觉特征，生成“画风提示词前缀”，保存到 6-12 个风格卡槽中。用户在导演台选择卡槽后，该前缀进入现有 `promptPrefix`，参与所有分镜的画面提示词生成。

本功能只提取画风，不复制参考图的具体主体、人物身份、场景、品牌、Logo 或原图文字。场景内容仍由旁白、视觉焦点和文字锚点决定。

### 不在首版范围内

- 不做模型微调、LoRA、Embedding 或风格训练。
- 不把参考图直接作为最终生图的 image-to-image 输入。
- 不自动识别并复刻特定在世艺术家姓名风格；模型输出应转化为色彩、材质、线条、构图、光影等描述。
- 不允许分析失败时保存空提示词卡槽。

## 2. 阿里百炼能力依据

本方案依据阿里百炼视觉理解文档（文档编号 `3026912`，访问地址：
`https://bailian.console.aliyun.com/cn-beijing?tab=doc#/doc/?type=model&url=3026912`）。文档当前给出的关键信息：

- `qwen3.7-plus`：推荐的视觉理解起点，支持文本、图像、视频输入和结构化输出。
- `qwen3.7-flash`：接近旗舰能力的低成本备选，支持结构化输出。
- 单张图片最高约 1600 万像素；图片越大，视觉 Token 消耗越高。
- Qwen3.7 系列支持结构化输出，适合要求模型返回稳定 JSON。

模型能力和价格可能变化，模型 ID 不得硬编码在业务逻辑中，必须放入后台配置并在服务测试时验证。

## 3. 总体架构

```text
前端上传参考图
       |
       v
POST /api/style-slots/analyze
       |
       +-- 图片尺寸/类型/大小校验
       +-- 本地临时保存或转 data URL
       +-- 阿里百炼 OpenAI 兼容 Chat Completions
       +-- 结构化 JSON 解析与字段校验
       +-- 画风/内容隔离校验
       v
返回候选风格前缀
       |
       +-- 用户编辑、调整强度
       +-- 保存到风格卡槽
       v
项目选择卡槽 -> promptPrefix 快照 -> 分镜提示词 -> 最终生图
```

视觉理解调用应独立于现有文本 LLM 配置。理由是：用户可能用一个文本模型生成旁白，用百炼视觉模型分析参考图；两者的模型能力、费用、超时和故障不应互相影响。

## 4. 后台配置设计

### 4.1 配置结构

在 `PixelleVideoConfig` 中新增：

```python
class VisionUnderstandingConfig(BaseModel):
    enabled: bool = False
    provider: str = "dashscope"
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen3.7-plus"
    fallback_model: str = "qwen3.7-flash"
    timeout_seconds: int = Field(default=60, ge=10, le=180)
    max_image_bytes: int = Field(default=10 * 1024 * 1024, ge=1_000_000)
    max_image_pixels: int = Field(default=16_000_000, ge=1_000_000)
    temperature: float = Field(default=0.2, ge=0, le=1)
```

挂载为：

```python
class PixelleVideoConfig(BaseModel):
    ...
    vision_understanding: VisionUnderstandingConfig = Field(
        default_factory=VisionUnderstandingConfig
    )
```

`base_url` 使用 OpenAI 兼容根地址，不要把 `/chat/completions` 写入配置。请求客户端统一拼接 `/chat/completions`。

### 4.2 推荐初始配置

```text
启用：关闭（首次配置后由用户手动打开）
提供商：阿里百炼
Base URL：https://dashscope.aliyuncs.com/compatible-mode/v1
主模型：qwen3.7-plus
降级模型：qwen3.7-flash
超时：60 秒
最大图片：10 MB，1600 万像素
温度：0.2
```

API Key 只在后端保存。GET 配置接口只返回 `api_key_set` 和掩码，不返回明文。

### 4.3 配置接口

扩展现有 `/api/config`：

```json
{
  "vision_understanding": {
    "enabled": true,
    "provider": "dashscope",
    "api_key": "sk-...",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen3.7-plus",
    "fallback_model": "qwen3.7-flash",
    "timeout_seconds": 60
  }
}
```

返回时使用：

```json
{
  "vision_understanding": {
    "enabled": true,
    "provider": "dashscope",
    "api_key_set": true,
    "api_key_masked": "sk-a...9z",
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen3.7-plus",
    "fallback_model": "qwen3.7-flash"
  },
  "service_status": {
    "vision_understanding": true
  }
}
```

新增服务测试：

```text
POST /api/config/test
{ "service": "vision_understanding", "config": {} }
```

测试请求只发送一段极小文本或一张内置测试图，不发送用户私有图片。结果需区分“配置完整”和“实际调用成功”。

## 5. 阿里百炼请求实现

### 5.1 请求协议

首版使用 OpenAI 兼容接口：

```text
POST {base_url}/chat/completions
Authorization: Bearer {DASHSCOPE_API_KEY}
Content-Type: application/json
```

请求体采用图像消息：

```json
{
  "model": "qwen3.7-plus",
  "temperature": 0.2,
  "messages": [
    {
      "role": "system",
      "content": "你是视觉风格分析器，只提取可迁移画风特征。"
    },
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/jpeg;base64,..."
          }
        },
        {
          "type": "text",
          "text": "请按照指定 JSON Schema 分析这张参考图的画风。"
        }
      ]
    }
  ],
  "response_format": { "type": "json_object" }
}
```

实际模型是否接受 `response_format` 应在服务测试中验证。如果当前模型或网关不接受该字段，重试时去掉该字段，但仍要求模型返回 JSON，并在后端做严格校验。

### 5.2 图片传输策略

首版默认使用后端转 data URL：

1. 校验 MIME 类型，仅允许 `image/jpeg`、`image/png`、`image/webp`。
2. 校验大小，默认不超过 10 MB。
3. 校验像素数，超过 1600 万像素时等比例缩放。
4. 去除 EXIF/GPS 元数据。
5. 转换为 JPEG 或 WebP 后编码为 data URL。
6. 请求结束后删除临时文件。

不把本地路径直接传给百炼。URL 方式只作为后续优化，并要求 URL 可被百炼访问、带有效期且不暴露项目目录。

## 6. 结构化输出协议

模型输出必须解析为以下结构：

```json
{
  "style_name": "复古丝网印刷插画",
  "style_prefix": "bold retro screen-print illustration, ...",
  "style_tags": ["复古", "有限色彩", "纸张颗粒"],
  "visual_features": {
    "medium": "",
    "linework": "",
    "color_palette": [],
    "lighting": "",
    "composition": "",
    "texture": "",
    "mood": ""
  },
  "content_excluded": ["人物身份", "具体地点", "原图文字"],
  "negative_constraints": ["do not copy the original subject"],
  "confidence": 0.88
}
```

后端必须执行：

- JSON 解析失败：按现有模型 JSON 修复策略重试一次。
- `style_prefix` 缺失或为空：视为失败，不保存卡槽。
- `style_prefix` 过长：限制为 1200 字符。
- `style_tags` 最多 12 项，每项最多 40 字符。
- `confidence` 限制在 0-1。
- 检查提示词是否包含明显原图主体描述；发现时剔除或要求模型重写。
- 清理 Markdown 代码围栏和模型解释性前后缀。

## 7. 风格提取系统提示词

建议固定在后端，不让前端覆盖：

```text
你是专业的视觉风格分析器。你的任务是从参考图中提取可迁移、可用于文生图的视觉语言。

只分析：媒介、线条、形状、色彩、材质、纹理、光影、构图、镜头语言、空间感和情绪。
严禁把参考图中的具体人物、脸、服装、地点、建筑、物体、品牌、Logo、日期和原图文字写入 style_prefix。
不要输出艺术家姓名来代替风格描述；将其转换成客观视觉特征。
style_prefix 必须是适合拼接到其他场景提示词前面的短英文提示词，80-180 个英文词以内。
negative_constraints 用于防止复制原图内容。
只返回 JSON，不要 Markdown，不要解释。
```

## 8. API 设计

### 8.1 分析接口

```text
POST /api/style-slots/analyze
Content-Type: multipart/form-data
```

字段：

```text
file: 图片文件
name: 可选，用户给出的风格名
```

成功返回：

```json
{
  "success": true,
  "analysis_id": "sa_...",
  "style": { "style_name": "...", "style_prefix": "..." },
  "preview_url": "/api/style-slots/analysis/sa_.../preview"
}
```

分析结果先保存为短期草稿，默认 30 分钟过期。只有用户点击保存时才写入正式卡槽。

### 8.2 卡槽接口

```text
GET    /api/style-slots
POST   /api/style-slots
PATCH  /api/style-slots/{slot_id}
DELETE /api/style-slots/{slot_id}
POST   /api/style-slots/{slot_id}/apply
```

`POST /api/style-slots` 必须要求非空 `style_prefix`，并接受用户编辑后的最终值。删除和覆盖操作需要前端确认。

### 8.3 应用接口

应用卡槽只修改当前导演台草稿，不直接修改历史项目：

```json
{
  "slot_id": "style_001",
  "target": "quick_create_draft"
}
```

提交项目时保存 `style_slot_id`、`style_prefix_snapshot`、`style_strength`，保证历史项目可复现。

## 9. 数据库设计

建议新增 `style_slots` 表：

```sql
CREATE TABLE style_slots (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  source_image_relative_path TEXT NOT NULL,
  thumbnail_relative_path TEXT NOT NULL,
  style_prefix TEXT NOT NULL,
  style_tags_json TEXT NOT NULL DEFAULT '[]',
  visual_features_json TEXT NOT NULL DEFAULT '{}',
  negative_constraints_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL,
  strength INTEGER NOT NULL DEFAULT 70,
  source TEXT NOT NULL DEFAULT 'user_upload',
  locked INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

参考图和缩略图存储在专用目录，例如 `data/style-slots/{slot_id}/`。数据库只保存相对路径，禁止保存任意用户路径。

## 10. 前端交互

在现有“画风提示词前缀”控件旁增加“风格卡槽”入口：

- 卡槽以缩略图 + 名称 + 3 个标签展示。
- 选中态必须明显，显示“已应用”。
- 提供“上传参考图提取画风”。
- 分析中显示进度和取消按钮。
- 分析完成后先进入“确认风格”面板，不自动覆盖用户当前前缀。
- 用户确认后才写入 `promptPrefix`。
- 修改过前缀后显示“已自定义”，避免用户误以为仍完全等同于卡槽。
- 选中其他卡槽覆盖前缀时必须提示将覆盖当前内容。
- 小屏幕使用横向滚动卡槽，不让 8 个卡槽挤压变形。

## 11. 故障与降级

| 场景 | 行为 |
|---|---|
| 未配置 API Key | 禁用分析按钮，提示去设置页配置 |
| 主模型超时/限流 | 使用 `fallback_model` 重试一次 |
| 两次都失败 | 不保存卡槽，保留用户图片和错误信息 |
| JSON 无法解析 | 自动修复一次，仍失败则报错 |
| 图片过大 | 后端等比压缩后继续 |
| 图片格式不支持 | 前端和后端都拒绝 |
| 返回内容混入原图主体 | 清洗并要求模型重写；仍不合格则失败 |
| 用户关闭视觉理解 | 保持现有手动 `promptPrefix` 流程可用 |

错误码建议：

```text
vision_understanding_not_configured
vision_image_invalid
vision_image_too_large
vision_model_timeout
vision_model_rate_limited
vision_response_invalid
style_prefix_empty
style_slot_limit_reached
```

## 12. 安全与隐私

- API Key 只存在后端配置，不进入浏览器日志、项目 JSON 或错误堆栈。
- 上传图片在调用百炼前明确提示“图片将发送至阿里云百炼进行分析”。
- 不记录图片 base64，不把完整请求体写入日志。
- 临时图片调用结束后删除；正式卡槽图片由用户主动保存。
- EXIF/GPS 信息在上传后剥离。
- 生成的前缀应避免输出人脸身份、敏感个人信息和原图文字。
- 参考图涉及人物时，前端提示用户确认其拥有使用权。

## 13. 实施拆分

### P0：后端能力

1. 增加 `VisionUnderstandingConfig` 和配置 API。
2. 实现 DashScope OpenAI 兼容客户端。
3. 实现图片校验、压缩、EXIF 清理和 data URL 编码。
4. 实现结构化响应解析和字段校验。
5. 实现 `/api/style-slots/analyze`。
6. 实现卡槽 SQLite 持久化和 CRUD。

### P1：前端能力

1. 设置页增加百炼视觉理解配置区。
2. 画风前缀区域增加 8 个风格卡槽。
3. 增加上传、分析、预览、编辑、保存和应用流程。
4. 将选中的卡槽写入 `promptPrefix`。
5. 提交项目时保存风格快照。

### P2：质量增强

1. 风格强度滑块。
2. 一键生成小尺寸测试图。
3. 主风格 + 辅助风格组合。
4. 风格一致性评分。
5. 卡槽导出/导入。

## 14. 测试与验收标准

### 后端测试

- 百炼配置能保存、读取时密钥被掩码。
- `qwen3.7-plus` 成功返回结构化风格结果。
- 主模型失败时只重试一次 `qwen3.7-flash`。
- JSON 包含 Markdown、额外解释或未转义引号时可恢复或明确失败。
- 空 `style_prefix` 不得保存。
- 原图主体不会进入最终 `style_prefix`。
- 10 MB 和 1600 万像素边界行为正确。
- 临时文件在成功、失败、超时后均清理。
- 卡槽删除不会删除其他卡槽资源。

### 前端测试

- 未配置视觉理解服务时分析按钮不可提交。
- 分析中按钮、取消、错误状态正确显示。
- 选择卡槽会更新前缀，但不会静默覆盖用户编辑内容。
- 重新选择卡槽有覆盖确认。
- 项目提交后的风格快照不会随卡槽后续编辑改变。
- 移动端 6-12 个卡槽可滚动且不溢出。

### 端到端验收

使用一张含明显纸张纹理、有限色彩和粗线条的参考图：

1. 上传成功。
2. 百炼返回风格名称、标签和非空前缀。
3. 前缀不包含参考图中的具体人物或场景。
4. 保存到卡槽并应用到导演台。
5. 生成两个不同旁白的分镜。
6. 两个分镜画面内容不同，但色彩、材质和线条保持统一。
7. 关闭视觉理解服务后，原有手动画风前缀流程仍然可用。

## 15. 推荐默认决策

- 卡槽数量：8 个，数据库允许扩展到 12 个。
- 首选模型：`qwen3.7-plus`。
- 降级模型：`qwen3.7-flash`。
- 首版只支持单图分析。
- 首版使用后端 data URL 传图，避免外网暴露本地文件。
- 首版不自动覆盖当前前缀，必须经过用户确认。
- 所有最终项目保存风格前缀快照。

