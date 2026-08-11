# 01 · 设计原则（Design Principles）

**版本**：1.0  
**适用范围**：`frontend/` 全部 React UI  
**落地入口**：优先 `frontend/src/index.css` 的 `@theme` 与 utility class，其次组件内 Tailwind。

---

## 1. 产品气质一句话

> **Soft Dark · Stage First · One Focus · Quiet Chrome**  
> 柔和深色 · 舞台优先 · 单焦点 · 安静的外壳

用户打开产品时的感受目标：

- 这是**创作工具**，不是后台配置台  
- 我始终知道**自己在哪一步**  
- 预览/结果是主角，参数是配角  
- 界面圆润、轻、不「锌板硬边」

---

## 2. 十大原则（决策时对照）

### P1 · 舞台优先（Stage First）

- 生成台：当前步骤主卡片 +（可选）分镜摘要；禁止多列参数同时抢焦点。  
- 精修台：预览区视觉权重最高（面积、对比、圆角阴影）。  
- **禁止**用等宽小字表格感占据预览应有的空间。

### P2 · 单焦点（One Focus Per Step）

- 快捷创作每步只突出 **1 个主任务** + **1 个主 CTA**。  
- 次要参数收入「高级」折叠，默认关闭。  
- 同时可见的「必填红框」不超过 1 个区块。

### P3 · 用户任务分组，非系统模块分组

| 用户问题 | 模块名（UI） | 禁止用的系统名（默认可见） |
|----------|--------------|---------------------------|
| 拍什么 | 内容 | LLM / prompt_prefix 裸露 |
| 长什么样 | 画面 | workflow id 优先展示 |
| 什么声音 | 配音与音乐 | inference_mode 技术词 |
| 字怎么出 | 字幕 | ASS/hyperframes 术语可进高级 |
| 好了吗 | 确认与生成 | task UUID 前置 |

技术标识可在高级区或设置中完整保留。

### P4 · 层级用面，少用线（Surfaces over Strokes）

- 默认：**背景差 + 圆角 + 轻阴影** 分区。  
- 硬边框 `border-zinc-800` 降级为：  
  - 输入框 focus 环  
  - 表格/列表分隔（可选 `divide-y`）  
  - 虚线空状态  
- 避免「每个小控件一圈线」造成蜂窝感。

### P5 · 圆润轻盈（Radius & Air）

- 卡片 / 面板大圆角；按钮中大圆角；胶囊用于状态。  
- 间距宁松勿挤：区块间 24px，卡片内 16–20px。  
- 主 CTA 有呼吸感（padding + 阴影），不要「细长条小按钮」。

### P6 · 主色克制（Brand Restraint）

- 琥珀（brand）**只用于**：主 CTA、进行中强调、关键选中、品牌点缀。  
- 正文、边框、次要按钮保持中性 zinc/slate。  
- 成功 emerald、警告 amber、错误 rose —— 语义色不用于装饰填满。

### P7 · 类型阶梯固定（Type Scale）

禁止随手 `text-[10px]` 堆砌。统一使用下方阶梯。

### P8 · 状态安静（Quiet Feedback）

- 生成中：舞台骨架 + 细进度，少连环 toast。  
- 错误：就地 inline，可重试。  
- 服务未就绪：顶栏一条可关闭引导，**不占侧栏半屏**。

### P9 · 一致可预期（Consistency）

- 同级按钮必须同一组件变体。  
- 同级卡片同一 radius / padding。  
- 左导航、步骤条、工作台顶栏的高度与节奏统一。

### P10 · 可访问与动效尊重（A11y & Motion）

- 焦点环可见（已有 amber focus-visible，保持）。  
- `prefers-reduced-motion` 时关闭位移动画（已有，保持）。  
- 图标按钮必须有 `aria-label`。

---

## 3. 视觉 Token（可执行）

### 3.1 颜色 — 写入 `index.css` `@theme`

在现有 surface 体系上**微调**（不推翻暗色）：

```css
/* 建议目标值（实现时可整块替换 @theme 相关段） */
--color-surface-0: #090a0e;   /* 页面底 */
--color-surface-1: #0e1015;   /* 侧栏 / 顶栏 */
--color-surface-2: #14161c;   /* 主卡片 */
--color-surface-3: #1b1e26;   /* 凹陷输入 / 次级面 */
--color-surface-4: #242833;   /* hover 抬起 */

--color-border-subtle: rgb(255 255 255 / 0.06);
--color-border-default: rgb(255 255 255 / 0.08);
--color-border-strong: rgb(255 255 255 / 0.12);

--color-text-primary: #f4f4f5;   /* zinc-100 */
--color-text-secondary: #a1a1aa; /* zinc-400 */
--color-text-tertiary: #71717a;  /* zinc-500 */
--color-text-disabled: #52525b;  /* zinc-600 */

--color-brand-400: #fbbf24;
--color-brand-500: #f59e0b;
--color-brand-600: #d97706;

--color-success: #34d399;
--color-warning: #fbbf24;
--color-danger: #fb7185;
```

**边框类映射（改造时批量替换思路）**：

| 旧习惯 | 新习惯 |
|--------|--------|
| `border-zinc-800` 满天飞 | 卡片：`border-[var(--color-border-subtle)]` 或无边框 + shadow |
| `bg-black` 输入 | `bg-[var(--color-surface-3)]` |
| `#17181c` 硬编码 | surface-3 / surface-2 变量 |

### 3.2 圆角

```css
--radius-xs: 0.375rem;   /* 6px  小芯片、kbd */
--radius-sm: 0.5rem;     /* 8px  小按钮、input 内嵌 */
--radius-md: 0.75rem;    /* 12px 默认按钮、小卡片 */
--radius-lg: 1rem;       /* 16px 主卡片、面板 */
--radius-xl: 1.25rem;    /* 20px 预览舞台、大空状态 */
--radius-pill: 9999px;   /* 状态胶囊、步骤点 */

--radius-card: var(--radius-lg); /* 覆盖现 0.75rem → 1rem */
```

Tailwind 使用约定：

- 按钮默认：`rounded-[var(--radius-md)]`  
- 主卡片：`rounded-[var(--radius-lg)]`  
- 预览舞台：`rounded-[var(--radius-xl)]`  
- Chip：`rounded-full`

### 3.3 阴影

```css
--shadow-soft: 0 1px 0 rgb(255 255 255 / 0.04) inset, 0 8px 24px rgb(0 0 0 / 0.28);
--shadow-stage: 0 0 0 1px rgb(255 255 255 / 0.06), 0 16px 48px rgb(0 0 0 / 0.45);
--shadow-cta: 0 4px 16px rgb(245 158 11 / 0.25);
--shadow-card: var(--shadow-soft);
```

### 3.4 间距（Spacing rhythm）

| Token | 值 | 用途 |
|-------|-----|------|
| `space-1` | 4px | 图标与文字 |
| `space-2` | 8px | 紧凑控件间隙 |
| `space-3` | 12px | 表单项内 |
| `space-4` | 16px | 卡片内边距（最小） |
| `space-5` | 20px | 卡片内边距（舒适） |
| `space-6` | 24px | 区块之间 |
| `space-8` | 32px | 步骤大分段 |
| `space-10` | 40px | 页面边距（宽屏） |

**生成台主列最大宽度**：`max-w-3xl`（约 768px）居中；宽屏可 `max-w-5xl` 且右侧固定摘要轨。  
**精修台**：全高 `h-full min-h-0`，预览区 `flex-1`。

### 3.5 字体阶梯

| 角色 | 规格 | Tailwind 等价 |
|------|------|----------------|
| Display | 20–24px / 700 / display | `text-xl font-bold font-display` |
| Title | 16px / 600 | `text-base font-semibold` |
| Body | 14px / 400 | `text-sm`（全局 body 已 14） |
| Label | 12px / 500 / secondary | `text-xs font-medium text-zinc-400` |
| Caption | 11–12px / tertiary | 用 `.text-caption`，**弃用随意 text-[10px]** |
| Mono | 时间码、ID | `font-mono text-xs text-zinc-500` |

### 3.6 动效

| 场景 | 时长 | 曲线 |
|------|------|------|
| Hover 颜色/边框 | 120–150ms | `ease-out` |
| 面板展开 | 180–220ms | `ease-out` |
| 页内步骤切换 | 200ms | fade + 轻微 y |
| 模态 | 200ms | soft-scale-in（已有） |

禁止：大面积弹跳、过长 skeleton 闪烁。

---

## 4. 布局原则

### 4.1 壳层（App Shell）

```
┌─ aside (导航) ─┬─ main (当前台) ──────────────────┐
│ 品牌            │ 可选：顶栏上下文                  │
│ 导航分组        │ 滚动内容 / 工作台全高             │
│ 底：精简状态    │ 可选：控制台抽屉                  │
└────────────────┴──────────────────────────────────┘
```

- 侧栏宽：`w-60`（240px）或 `w-56`（224px），比现 `w-64` 略收，让主舞台更大。  
- 侧栏背景：`surface-1`，**不要**和主区同色糊成一片。  
- 主区背景：`surface-0`。

### 4.2 生成台内容列

- 垂直节奏：**步骤条 → 主卡片 → 次要折叠 → 底栏 CTA 条（sticky）**。  
- sticky 底栏：模糊半透明 `surface-1/90 backdrop-blur`，主按钮右对齐。

### 4.3 精修台

- **禁止**超过 2 条「全宽工具横条」同时常驻；多余收入菜单/抽屉。  
- 三栏最小宽：左 220 / 中 flex / 右 280（可参考现 grid 微调 radius 与间距）。

---

## 5. 文案与语气

| 场景 | 语气 | 示例 |
|------|------|------|
| 主 CTA | 动词短句 | 生成项目、导出成片 |
| 空状态 | 鼓励 + 一步行动 | 还没有项目，从一条主题开始 |
| 错误 | 人话 + 下一步 | 配音未配置，去设置或改用 Edge |
| 技术细节 | 收进高级 | 模型 ID、endpoint |

中文优先完整句；少用「异常」「失败码」裸奔。

---

## 6. 图标

- 继续 Lucide。  
- 默认 stroke 1.5–2；导航图标 16–18px。  
- 主 CTA **可**带图标，次要按钮慎用，避免图标丛林。

---

## 7. 与现有代码的映射

| 现有 | 改造动作 |
|------|----------|
| `index.css` `@theme` surface / radius-card | 扩展 token（第 3 节） |
| `.ui-card` / `.ui-panel` | 加大 radius，弱化 border，加强 soft shadow |
| `.text-caption` / `.text-label` | 保留，全站替换 `text-[10px]` |
| `App.tsx` 侧栏 `border-zinc-800` | 改 subtle border + surface-1 |
| `QuickCreate` 长表单卡片 | 按线框拆步骤主卡片 |
| `ProjectWorkbench` 多横条 | 合并顶栏，舞台圆角 |

---

## 8. 验收（原则级）

- [ ] 任意截图：能指出「主 CTA」「主内容」「次要信息」三层  
- [ ] 硬边框数量显著少于改造前  
- [ ] 预览/主卡片圆角 ≥ 16px  
- [ ] 默认路径下，用户不必先读服务状态才能创作  
- [ ] 无新增功能、无 API 变更  

---

## 9. 反模式清单（Review 时直接打回）

1. 新页面又铺满 `border border-zinc-800` 小格子。  
2. 主按钮与次按钮都用琥珀实心。  
3. 预览区小于侧栏参数区。  
4. 一步里塞 3 个以上「必填」区块。  
5. 为对齐而用 `text-[9px]` / `text-[10px]`。  
6. 动画超过 300ms 或弹跳。  
