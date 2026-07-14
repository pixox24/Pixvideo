# Pixvideo

Pixvideo 是一个 AI 短视频生成工具。输入主题、脚本或素材后，可串联文案生成、语音合成、图像/视频生成、模板渲染和视频合成流程，帮助快速制作短视频内容。

## 功能

- 主题生成视频：根据主题自动生成脚本、画面提示词、语音和成片。
- 自定义脚本：使用已有文案生成配音、画面和视频。
- 多种流水线：支持标准视频、图生视频、数字人口播、动作迁移等创作方式。
- Web 工作台：通过浏览器完成配置、任务创建、预览和历史管理。
- 生产安全：支持逐分镜画面提示、独立批量任务、生成前核对、草稿恢复、幂等提交、取消和一致的历史状态。
- 可扩展配置：支持不同 LLM、TTS、ComfyUI/RunningHub 工作流和视频模板。

## 环境要求

- Python 3.11+
- Node.js 22+
- uv
- ffmpeg

macOS 可使用 Homebrew 安装 ffmpeg：

```bash
brew install ffmpeg
```

## 快速开始

```bash
git clone <your-repo-url>
cd Pixvideo
uv sync
cp config.example.yaml config.yaml
cd frontend && npm ci && npm run build && cd ..
uv run python api/app.py --host 127.0.0.1 --port 8000
```

启动后打开：

```text
http://localhost:8000
```

也可以直接运行启动脚本：

```bash
./start_web.sh
```

Windows 用户可运行：

```bat
start_web.bat
```

## 配置

首次运行前，请复制并编辑配置文件：

```bash
cp config.example.yaml config.yaml
```

常见配置项包括：

- LLM 服务与 API Key
- TTS 服务
- 图像/视频生成工作流
- 输出目录
- 模板与视频参数

## 常用命令

```bash
# 构建并启动 Web 界面与 API
cd frontend && npm run build && cd ..
uv run python api/app.py --host 127.0.0.1 --port 8000

# 前端热更新开发服务器（端口 5173）
cd frontend && npm run dev

# 运行示例生成脚本
uv run python generate_video.py

# 运行测试
uv run --extra dev pytest

# 代码检查
uv run --extra dev ruff check .
```

## 目录结构

```text
api/             FastAPI 接口
frontend/        React Web 工作台
pixelle_video/   核心生成逻辑与服务模块
templates/       视频画面模板
resources/       示例资源与静态文件
tests/           测试用例
docs/            项目文档
```

> 说明：当前 Python 包目录仍保留为 `pixelle_video/`，这是代码导入路径的一部分，重命名前需要同步调整引用与测试。

## License

Apache-2.0
