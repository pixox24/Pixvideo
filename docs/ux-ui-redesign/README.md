# PixVideo UX/UI 纯界面改造文档包

**日期**：2026-08-10（执行叠加层 05：2026-08-20）  
**范围**：**不改业务功能与 API 契约**，仅优化信息架构呈现、布局、视觉层级与交互质感。  
**目标气质**：流程清晰 · 布局合理 · 层级明确 · **圆润轻盈（Soft Dark）** · 舞台优先。

---

## 文档索引

| # | 文档 | 用途 |
|---|------|------|
| 1 | [01-design-principles.md](./01-design-principles.md) | 设计原则、视觉 token、文案与动效准则（落地 CSS/Tailwind 的唯一真相源） |
| 2 | [02-wireframes-create-edit.md](./02-wireframes-create-edit.md) | 生成台 / 精修台文字线框、区块职责、响应式断点、DOM 结构建议 |
| 3 | [03-component-spec.md](./03-component-spec.md) | 组件规范：按钮/卡片/输入/步骤条/时间线/导航/空状态等（含 class 映射） |
| 4 | [04-implementation-plan.md](./04-implementation-plan.md) | 分 PR 实施计划、文件清单、验收标准、风险与回滚（PR-A–G 骨架） |
| 5 | [05-stage-first-execution.md](./05-stage-first-execution.md) | Stage First 缺口收口执行计划（P0–P2，对照现网代码；A–F 之后的叠加层） |

**关联文档**（业务向，勿与本包混淆）：

- `docs/plans/2026-08-10-semantic-storyboard-count-plan.md` — 语义分镜（含逻辑）
- `docs/superpowers/specs/2026-08-06-ai-editing-workbench-design.md` — 工作台功能设计

---

## 双壳产品叙事（全篇共用）

```
生成台 Create  = 快捷创作（QuickCreate）  → 轻、步骤、大输入
精修台 Edit    = 项目工作台（ProjectWorkbench） → 预览中心、时间线
作品库 Library = 历史记录（HistoryList）
设置 Settings  = 系统设置（SystemSettingsTab）
```

侧栏导航建议文案（可分阶段替换，P0 可仅改视觉不改路由 key）：

| 现 key | 现文案 | 建议展示文案 |
|--------|--------|--------------|
| `quick-create` | 快捷创作 | 开始创作 |
| `project-workbench` | 项目工作台 | 精修 |
| `history` | 历史记录 | 作品库 |
| `settings` | 系统设置 | 设置 |

---

## 改造边界（强制）

### 允许

- `frontend/src/**/*.tsx|ts|css` 样式与布局结构
- 纯展示组件拆分（不改变 props 业务语义）
- 文案标签、空状态、骨架屏、间距圆角
- 折叠/展开默认状态（不删除功能入口）

### 禁止

- 修改 API 请求/响应字段与后端逻辑
- 删除或合并会改变业务结果的步骤
- 改生成管线、TTS/字幕算法、分镜 pack 规则（另案）
- 为「好看」隐藏不可达的关键配置（可默认折叠，必须可展开）

---

## 建议阅读顺序

1. 原则 → 2. 线框 → 3. 组件 → 4. 实施计划（A–F 骨架）→ 5. Stage First 收口执行 → 按 PR-H 起开工。
