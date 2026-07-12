# 架构设计

Pixelle-Video 的技术架构概览。

---

## 核心架构

Pixelle-Video 采用分层架构设计：

- **Web 层**: 由 FastAPI 托管的 React/Vite 工作台
- **API 层**: 为工作台和外部客户端提供的 FastAPI 路由
- **服务层**: 核心业务逻辑
- **ComfyUI 层**: 图像和TTS生成

---

## 主要组件

### PixelleVideoCore

核心服务类，协调各个子服务。

### LLM Service

负责调用大语言模型生成文案。

### Image Service

负责调用 ComfyUI 生成图像。

### TTS Service

负责调用 ComfyUI 生成语音。

### Video Generator

负责合成最终视频。

---

## 技术栈

- **后端**: Python 3.11+, FastAPI, AsyncIO
- **Web**: React、Vite、FastAPI 静态文件托管
- **AI**: OpenAI API, ComfyUI
- **配置**: YAML
- **工具**: uv (包管理)

---

## 更多信息

详细的架构文档即将推出。
