# 04 · 纯 UI 改造实施计划（分 PR 可执行）

**版本**：1.0  
**类型**：前端-only，**零业务逻辑变更**  
**预估**：1 人全职约 8–12 个工作日（可按 PR 并行）  
**依赖文档**：`01` 原则 · `02` 线框 · `03` 组件规范  

---

## 0. 总原则

1. **每个 PR 可独立合并**：合并后产品可用，允许渐进变美。  
2. **禁止**改 API、store 业务语义、生成算法、分镜 pack 规则。  
3. **允许**拆展示组件、改 className、默认折叠、文案标签。  
4. 每个 PR 附：**截图前后对比**（生成台 + 精修台至少各一）。  
5. 回归：手动点一遍「生成文案 → 进工作台 → 播放 → 导出对话框打开」。

### 推荐分支策略

```
main
 └── ui/soft-dark-foundation     PR-A
      └── ui/app-shell-nav       PR-B
           ├── ui/create-stepper-layout   PR-C
           └── ui/workbench-stage         PR-D
                └── ui/history-polish     PR-E（可与 D 并行）
```

---

## 1. PR 总览

| PR | 名称 | 预估 | 风险 | 用户可感知 |
|----|------|------|------|------------|
| **A** | 设计 Token + 全局基础类 | 1d | 低 | 圆角/颜色轻微统一 |
| **B** | App Shell + 侧栏导航 | 1d | 低 | 导航更轻、状态折叠 |
| **C** | 生成台步骤化布局 | 2–3d | 中 | 流程清晰、sticky CTA |
| **D** | 精修台舞台化 | 2–3d | 中 | 预览大、顶栏干净 |
| **E** | 作品库卡片 + 空状态 | 1d | 低 | 历史页变作品墙 |
| **F** | 设置页与控件收尾 | 1d | 低 | 设置不那么「表」 |
| **G** | ui/ 组件收敛（可选） | 1–2d | 低 | 长期可维护 |

**建议最小闭环**：A → B → C → D。E/F/G 可随后。

---

## 2. PR-A · 设计 Token 与全局基础

### 2.1 目标

落地 `01` 中的 color / radius / shadow / typography utility，升级 `.ui-card` / `.ui-panel`。

### 2.2 改动文件

| 文件 | 动作 |
|------|------|
| `frontend/src/index.css` | 扩展 `@theme`；新增 CSS 变量；升级 `.ui-card` `.ui-panel`；新增 `.ui-btn*` `.ui-input` `.ui-stage` `.ui-chip` |
| （可选）`frontend/src/components/ui/README.md` | 指向 `03-component-spec.md` |

### 2.3 任务清单

- [x] 写入 surface / border / radius / shadow 变量  
- [x] `.ui-card`：`radius-lg`、subtle border、`shadow-soft`  
- [x] `.ui-panel`：对齐规范  
- [x] 新增 `.ui-btn-primary` / `.ui-btn-secondary` / `.ui-btn-ghost` / `.ui-input` / `.ui-stage`  
- [x] 确认 `prefers-reduced-motion` 与 focus-visible 仍生效  
- [x] 全局扫一眼：无大面积回归（仅 token 时页面应几乎不变或略柔）  
- **落地**：`frontend/src/index.css` + `frontend/src/components/ui/README.md`（2026-08-10）

### 2.4 验收

- [ ] `npm run build`（或项目既有 frontend build）通过  
- [ ] 浏览器硬刷新后无样式炸裂  
- [ ] 文档 token 与 CSS 变量名一致  

### 2.5 回滚

还原 `index.css` 即可。

---

## 3. PR-B · App Shell 与侧栏

### 3.1 目标

侧栏 soft dark、导航 active 态、底栏服务状态**默认折叠**、主区背景 surface-0。

### 3.2 改动文件

| 文件 | 动作 |
|------|------|
| `frontend/src/App.tsx` | `navBtn` class；aside 宽与色；底栏折叠默认；可选导航展示文案 |
| `frontend/src/components/ConsolePanel.tsx` | 圆角与边框弱化（不改逻辑） |
| `frontend/src/components/Toast.tsx` | 圆角/阴影（若存在） |

### 3.3 任务清单

- [x] `aside`：`bg-[var(--color-surface-1)]`，border 用 subtle  
- [x] 导航 active：`bg-amber-500/10 ring-1 ring-amber-500/20`  
- [x] 服务状态：`statusExpanded` 默认 `false`（现若为 false 则保持）  
- [x] 就绪摘要一行：`服务状态 · 3/6`  
- [x] 移动端遮罩：`backdrop-blur-sm`  
- [x] （可选）展示文案：开始创作 / 精修 / 作品库 / 设置（**不改** `ActiveTab` 枚举值）  
- **落地**：`App.tsx` + `ConsolePanel.tsx` + `Toast.tsx` + `tests/frontend/test_app_shell_nav.py`（2026-08-11）

### 3.4 验收

- [ ] 四导航切换正常  
- [ ] 点状态行可展开服务列表并跳转设置  
- [ ] 预设名仍显示  
- [ ] 控制台开合正常  

### 3.5 不包含

改路由结构、加新页面、动 QuickCreate 内部。

---

## 4. PR-C · 生成台步骤化布局

### 4.1 目标

QuickCreate 按 `02` 四步主卡片 + 顶部 Stepper + sticky 底栏；高级区折叠；**不改**提交 payload 与 state 字段语义。

### 4.2 改动文件

| 文件 | 动作 |
|------|------|
| `frontend/src/components/QuickCreate.tsx` | 布局重组（最大文件，可只分区 class） |
| `frontend/src/components/quickCreate/wizard.ts` | 步骤 id/文案与四步对齐（若需） |
| `frontend/src/components/quickCreate/CreateStepper.tsx` | **新建**（可选，纯展示） |
| `frontend/src/components/quickCreate/CreateStickyFooter.tsx` | **新建**（可选） |
| `frontend/src/components/SubtitleStylePreview.tsx` | 包进折叠时样式微调 |
| `tests/frontend/test_quick_create_*.py` | 更新文案/结构契约断言 |

### 4.3 任务清单

- [x] 顶部：标题行 + `CreateStepper`（内容/风格/声音/确认）  
- [x] `wizardStep` 控制**主卡片可见性**（新手）；专家模式仍可多卡纵向  
- [x] 将现有 DOM **剪切分组**进四步（禁止删字段）  
  - 内容：主题、文案、分镜数、切分、字数、关键词  
  - 风格：画幅、workflow、前缀、运动/字幕、字幕高级  
  - 声音：TTS 全套、BGM  
  - 确认：review 列表、勾选、复用  
- [x] sticky footer：上一步 / 下一步 / 最终主 CTA（绑定现有 `handleTriggerRender` 等）  
- [ ] 关键词、字幕细调、voice design：更深折叠（P1 打磨；既有高级区保留）  
- [x] 主卡片统一 `ui-card`（主要 stage）  
- [x] 分镜数量数字输入样式对齐 `ui-input`  
- [ ] （xl）可选右侧摘要：只读分镜列表（后续打磨）  
- **落地**：`wizard.ts` + `CreateStepper.tsx` + `CreateStickyFooter.tsx` + `QuickCreate.tsx` + `tests/frontend/test_quick_create_wizard_ui.py`（2026-08-11）

### 4.4 明确禁止

- 修改 `handleGenerateCopyDraft` / `handleTriggerRender` 的请求 body 字段名  
- 删除 mode：`ai | manual | batch`  
- 改变语义分镜 pack 算法（已在 storyboardSplit）

### 4.5 验收

- [ ] 新手四步能走完并成功创建项目/任务（与改前同一 API）  
- [ ] 专家模式仍能一页看到关键项  
- [ ] 预设加载/保存 UI 仍可用  
- [ ] TTS 试听、BGM 试听仍可用  
- [ ] 契约测试更新并通过  
- [ ] 窄屏：步骤可横滑或换行，不横向撑破  

### 4.6 回滚

以 PR 为单位 revert；state 未改则数据无影响。

---

## 5. PR-D · 精修台舞台化

### 5.1 目标

合并顶栏横条；预览 `ui-stage`；BGM 等进项目设置抽屉；时间线 panel 化；**零播放/导出逻辑变更**。

### 5.2 改动文件

| 文件 | 动作 |
|------|------|
| `frontend/src/components/ProjectWorkbench.tsx` | 顶栏、舞台、抽屉入口、横条合并 |
| `frontend/src/components/WorkbenchTimeline.tsx` | 容器与轨道 class |
| `frontend/src/components/SceneList.tsx` | 行样式 |
| `frontend/src/components/SceneInspector.tsx` | 分组/Tab 视觉（可仅 CSS） |
| `frontend/src/components/GenerationRunPanel.tsx` | slim 条样式 |
| `frontend/src/components/GenerationQueue.tsx` | 默认折叠外观 |
| `frontend/src/components/ExportDialog.tsx` | 圆角与按钮 variant |
| `tests/frontend/test_workbench_*.py` | 仅当断言了旧 class/文案时更新 |

### 5.3 任务清单

- [x] TOPBAR 单行：标题、状态胶囊、导出 primary、刷新 ghost、**项目设置**按钮  
- [x] 将 BGM/音量/字幕勾选/保存设置移入 Drawer（state 仍用现 `settings` / `saveSettings`）  
- [x] 快捷键 tip：保留 dismiss；样式改 banner  
- [x] 中部 grid：左 SceneList / 中 Stage / 右 Inspector  
- [x] Stage：`ui-stage` + 大圆角；播放控件圆形  
- [x] 批量工具条：仅 `selectedSceneIds.size > 0` 时显示  
- [x] Timeline 外包 `ui-panel`/`rounded-xl`  
- [x] GenerationQueue 默认收起为摘要芯片  
- [x] 确认 `audioRef` / `bgmAudioRef` / rAF 播放逻辑保留（仅 UI 包装）  
- **落地**：`ProjectWorkbench` + 周边组件 + `tests/frontend/test_workbench_stage_ui.py`（2026-08-11）

### 5.4 验收

- [ ] 播放、空格、方向键与改前一致  
- [ ] 导出对话框仍能提交（只测打开与字段，不强制真导出）  
- [ ] 分镜切换、检查器保存、重生成按钮仍在  
- [ ] 时间线拖拽/缩放/撤销仍可用  
- [ ] 生成 run 面板按钮仍可点  
- [ ] 移动端分镜/预览/属性切换仍可用  

### 5.5 风险

- **高**：Workbench 文件大，易误删 handler。  
  **缓解**：先只包 wrapper div 与 class；逻辑块整段搬移时用编辑器「折叠移动」。  
- 播放回归：重点回归 PR-D。

---

## 6. PR-E · 作品库（历史）

### 6.1 文件

- `frontend/src/components/HistoryList.tsx`  
- `frontend/src/components/EmptyState.tsx`（若有）

### 6.2 任务

- [x] 列表 → 响应式卡片网格 `grid sm:2 lg:3`  
- [x] 卡片：封面占位、标题、分镜数、时间 caption、主操作  
- [x] 空状态：软卡片（无 tab 回调时不强制 CTA）  
- [x] 排序控件样式统一  
- **落地**：`HistoryList.tsx` + `EmptyState.tsx` + `tests/frontend/test_history_library_ui.py`（2026-08-11）

### 6.3 验收

- [x] 打开历史、筛选/排序、进入项目/复制等原操作仍在  

---

## 7. PR-F · 设置页收尾

### 7.1 文件

- `frontend/src/components/SystemSettingsTab.tsx`

### 7.2 任务

- [x] 分区卡片化（LLM / 图像 / Comfy / TTS Keys）`ui-card`  
- [x] 输入统一 `ui-input`  
- [x] 测试连接按钮 secondary；保存 primary  
- [x] 说明文字用 caption，减少 10px  
- **落地**：`SystemSettingsTab.tsx` + `tests/frontend/test_settings_ui.py`（2026-08-11）

### 7.3 验收

- [x] 保存配置、测试连接 API 仍成功（逻辑未改）

---

## 8. PR-G · 可选 ui 组件库收敛

### 8.1 任务

- [ ] 新增 `components/ui/Button.tsx` 等  
- [ ] 逐步替换 App / QuickCreate / Workbench 中重复 class  
- [ ] 每个替换 PR 要小，避免巨 diff  

---

## 9. 测试策略

### 9.1 自动化

| 类型 | 命令/位置 | 何时跑 |
|------|-----------|--------|
| 前端契约 | `pytest tests/frontend/ -q` | 每 PR |
| storyboard 单测 | `node --import tsx --test frontend/src/lib/storyboardSplit.test.ts` | 若未改可跳过 |
| tsc | `cd frontend && npx tsc --noEmit` | 每 PR |
| build | 项目既有 frontend build | 合并前 |

### 9.2 手动清单（全 PR 合并后）

1. 冷启动 → 开始创作  
2. 生成文案 → 分镜数建议显示  
3. 走完四步 → 进入精修  
4. 播放/暂停/seek  
5. 改旁白保存（若有）  
6. 打开导出对话框  
7. 作品库打开一条  
8. 设置页保存（可用假操作）  
9. 窄屏 375 宽：导航抽屉、工作台三面板切换  

---

## 10. 文件总清单（快速检索）

```
frontend/src/index.css                          # PR-A
frontend/src/App.tsx                            # PR-B
frontend/src/components/QuickCreate.tsx         # PR-C
frontend/src/components/quickCreate/*           # PR-C
frontend/src/components/ProjectWorkbench.tsx    # PR-D
frontend/src/components/WorkbenchTimeline.tsx   # PR-D
frontend/src/components/SceneList.tsx           # PR-D
frontend/src/components/SceneInspector.tsx      # PR-D
frontend/src/components/GenerationRunPanel.tsx  # PR-D
frontend/src/components/GenerationQueue.tsx     # PR-D
frontend/src/components/ExportDialog.tsx        # PR-D
frontend/src/components/HistoryList.tsx         # PR-E
frontend/src/components/SystemSettingsTab.tsx   # PR-F
frontend/src/components/Toast.tsx               # PR-B/A
frontend/src/components/ConsolePanel.tsx        # PR-B
frontend/src/components/ui/*                    # PR-G
tests/frontend/test_quick_create_*.py           # PR-C
tests/frontend/test_workbench_*.py              # PR-D 按需
docs/ux-ui-redesign/*                           # 本文档包
```

---

## 11. 里程碑与定义完成（DoD）

### M1 基础（A+B）

- Soft dark 导航与 token 生效  
- 服务状态不抢戏  

### M2 生成清晰（C）

- 用户能指着屏幕说出「我在第几步」  
- 主 CTA 固定、好点  

### M3 精修好看（D）

- 预览是视觉中心  
- 顶栏不再「条纹化」  

### M4 完整（E+F）

- 作品库像作品  
- 设置像设置页而非调试台  

### 全局 DoD

- [ ] 无 API/后端 diff  
- [ ] 核心用户路径手动通过  
- [ ] 前后截图贴在 PR 描述  
- [ ] 契约测试绿  

---

## 12. 风险登记

| 风险 | 影响 | 缓解 |
|------|------|------|
| QuickCreate 过大难拆 | C 延期 | 先 class 分区，后拆文件 |
| Workbench 误改播放 | 播放回归 | D 禁止改 hooks 依赖与 ref 逻辑 |
| 契约测试绑死旧文案 | CI 红 | 断言行为/关键文案，少绑 class |
| 设计过度折叠 | 找不到功能 | 每步保留「高级」入口；评审用功能保全清单 |

---

## 13. 实施启动检查表（给执行者）

开工前：

- [ ] 读完 `01` `02` `03`  
- [ ] 本地 frontend dev 可跑  
- [ ] 建分支 `ui/soft-dark-foundation`  
- [ ] PR-A 只动 CSS，先合并建立基线  

每 PR 描述模板：

```markdown
## 目标
（一句话）

## 截图
| Before | After |
|--------|-------|

## 功能确认
- [ ] 无 API 变更
- [ ] 路径：创作 → 精修 → 播放

## 测试
- [ ] tsc
- [ ] pytest tests/frontend/...
```

---

## 14. 与后续「可能的功能 PR」隔离

以下**不要**混进 UI PR：

- 语义分镜扩写到严格 N  
- 新 API  
- 字幕/TTS 算法  
- 工作台多轨视频  

UI 做完后另开 epic。

---

## 15. 时间表示例（1 人）

| 日 | 工作 |
|----|------|
| D1 | PR-A + PR-B |
| D2–D4 | PR-C |
| D5–D7 | PR-D |
| D8 | PR-E + 回归 |
| D9 | PR-F + 打磨 |
| D10 | PR-G 或 buffer |

---

**文档结束。** 执行时以本文件 PR 清单为看板；原则冲突时以 `01-design-principles.md` 为准，线框冲突以 `02` 为准，组件细节以 `03` 为准。
