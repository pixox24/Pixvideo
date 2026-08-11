# 03 · 组件规范清单（可落地代码）

**版本**：1.0  
**实现策略**：  
1. 先在 `frontend/src/index.css` 增加 utility / 组件类  
2. 再抽 `frontend/src/components/ui/*`（Button、Input、Card…）逐步替换  
3. **P0 允许**先用 Tailwind 长 class 字符串对齐本规范，P1 再收敛组件  

**原则引用**：`01-design-principles.md` tokens。

---

## 0. 命名约定

| 类型 | 前缀 | 示例 |
|------|------|------|
| CSS 工具类 | `ui-` | `ui-btn`, `ui-card`, `ui-input` |
| React 组件 | PascalCase | `UiButton`, `UiCard`（可选） |
| 变体 prop | `variant` / `size` | `variant="primary"` |

现有 `.ui-card` / `.ui-panel` **升级而非删除**。

---

## 1. 按钮 Button

### 1.1 变体

| variant | 用途 | 视觉 |
|---------|------|------|
| `primary` | 主 CTA：生成、导出、保存关键 | 实心 brand-500，文字 black，shadow-cta |
| `secondary` | 次要行动：试听、刷新 | surface-3 面，subtle 边框，text-primary |
| `ghost` | 工具栏、图标旁文字 | 透明，hover surface-3 |
| `danger` | 删除 | 透明/浅 rose 边，text rose |
| `outline` | 次要替代 | 仅 border-strong |

### 1.2 尺寸

| size | height | padding | 字号 | 圆角 |
|------|--------|---------|------|------|
| `sm` | 32px | px-3 | 12px | radius-md |
| `md` | 40px | px-4 | 14px | radius-md |
| `lg` | 48px | px-6 | 14–15px semibold | radius-md |
| `icon` | 36×36 | p-0 | — | radius-md |
| `icon-lg` | 44×44 圆形播放 | — | — | full |

### 1.3 状态

- `disabled`：opacity 0.4，`pointer-events-none`  
- `loading`：左侧 Loader 转圈，保持宽度防抖  

### 1.4 推荐 class（可直接粘贴）

```txt
# primary md
inline-flex items-center justify-center gap-2 h-10 px-4 rounded-[var(--radius-md)]
bg-amber-500 text-black text-sm font-semibold shadow-[var(--shadow-cta)]
hover:bg-amber-400 transition-colors disabled:opacity-40

# secondary md
inline-flex items-center justify-center gap-2 h-10 px-4 rounded-[var(--radius-md)]
bg-[var(--color-surface-3)] text-zinc-100 text-sm font-medium
border border-[var(--color-border-subtle)]
hover:bg-[var(--color-surface-4)] transition-colors

# ghost icon
inline-flex items-center justify-center h-9 w-9 rounded-[var(--radius-md)]
text-zinc-400 hover:text-zinc-100 hover:bg-[var(--color-surface-3)] transition-colors
```

### 1.5 替换地图

| 现位置 | 现样式特征 | 目标 variant |
|--------|------------|--------------|
| 导出成片、开始生成 | `bg-amber-500 ... text-black` | primary |
| 保存设置、试听 | border + 小字 | secondary |
| 时间线图标按钮 | `p-2 text-zinc-400` | ghost icon |
| 删除预设 | 红字/边框 | danger |

---

## 2. 卡片 Card / 面板 Panel

### 2.1 `ui-card`（主内容块）

```css
.ui-card {
  border-radius: var(--radius-lg); /* 16px */
  border: 1px solid var(--color-border-subtle);
  background: var(--color-surface-2);
  box-shadow: var(--shadow-soft);
  padding: 1.25rem; /* 20px，可用 p-5 */
}
```

可选 header 槽：

```
┌ ui-card ─────────────────────┐
│ title (semibold)   action    │
│ description caption          │
│ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │  optional divider
│ children                     │
└──────────────────────────────┘
```

### 2.2 `ui-panel`（凹陷/次级）

```css
.ui-panel {
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-surface-3);
  padding: 0.75rem 1rem;
}
```

用于：摘要轨、检查器内分组、时间线外框。

### 2.3 `ui-stage`（预览舞台）

```css
.ui-stage {
  border-radius: var(--radius-xl);
  background: #050506;
  box-shadow: var(--shadow-stage);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
```

---

## 3. 输入 Input / Textarea / Select

### 3.1 文本输入

```txt
h-10 w-full rounded-[var(--radius-md)] px-3 text-sm text-zinc-100
bg-[var(--color-surface-3)] border border-[var(--color-border-subtle)]
placeholder:text-zinc-600
focus:outline-none focus:border-amber-500/60 focus:ring-2 focus:ring-amber-500/20
transition-colors
```

- `type="number"`：同高，可 `tabular-nums`。  
- 错误：`border-rose-500/50 focus:ring-rose-500/20` + 下方 caption 错误文案。

### 3.2 Textarea

- 同上 + `py-2.5 min-h-[88px] resize-y`  
- 主题/文案主输入：`min-h-[120px]`

### 3.3 Select

- 与 Input 同高同圆角；自定义 `Select.tsx` 若存在，统一套 surface-3。  
- 避免原生 select 在 macOS 上过高不齐：固定 `h-10`。

### 3.4 Label

```txt
mb-1.5 block text-xs font-medium text-zinc-400
```

可选 `hint`：`mt-1 text-caption`

### 3.5 分段控件 Segmented control（TTS 模式、画幅）

```
┌────────┬────────┬────────┐
│ Edge   │ MiniMax│  MiMo  │  ← 整组 rounded-lg p-1 bg-surface-3
└────────┴────────┴────────┘
选中项：bg-surface-2 或 brand/10 + text-amber-400 + 小阴影
```

高度 36–40px；移动端可横滑。

---

## 4. 步骤条 Stepper

### 4.1 结构

```
(1) 内容 ────── (2) 风格 ────── (3) 声音 ────── (4) 确认
 done            current          todo            todo
```

### 4.2 状态

| 状态 | 圆点 | 文案 | 连接线 |
|------|------|------|--------|
| todo | 空心 border | tertiary | tertiary |
| current | brand 实心 / ring | primary | brand 半 |
| done | brand 实心 + check | secondary | brand |

### 4.3 交互

- 点击 **done** 步：允许回退。  
- 点击 **todo**：仅专家模式或已解锁时允许。  
- 移动端：可变为横向 scroll 的 chip 条。

### 4.4 与代码映射

- 数据源：`WIZARD_STEPS` / `wizard.ts`  
- 展示层新建 `CreateStepper.tsx` 或在 QuickCreate 顶部。  
- 现「仅 anchor 滚动」升级为 **步进状态机 UI**（state 仍可用 `wizardStep`）。

---

## 5. 导航 Nav Item

### 5.1 侧栏项

```txt
# inactive
w-full flex items-center gap-2.5 px-3 py-2.5 rounded-[var(--radius-md)]
text-sm font-medium text-zinc-400 hover:text-zinc-100 hover:bg-white/5

# active
... text-zinc-50 bg-amber-500/10 ring-1 ring-amber-500/20
```

图标 `h-4 w-4`；分组标题：`text-caption uppercase tracking-wider px-3 mb-1 mt-4`

### 5.2 替换

`App.tsx` → `navBtn()` 函数按上表改写。

---

## 6. 状态胶囊 Chip / Badge

| 语义 | class 思路 |
|------|------------|
| success / ready | `bg-emerald-500/15 text-emerald-300 rounded-full px-2 py-0.5 text-xs` |
| warning / missing | `bg-amber-500/15 text-amber-200 ...` |
| running | `bg-sky-500/15 text-sky-200` + 可选 pulse 点 |
| neutral | `bg-white/5 text-zinc-400` |

用于：服务状态、分镜生成态、导出态。

---

## 7. 时间线 Timeline

### 7.1 容器

```txt
rounded-[var(--radius-lg)] bg-[var(--color-surface-2)]
border border-[var(--color-border-subtle)] p-2
```

### 7.2 轨道片段

```txt
rounded-lg h-10 bg-[var(--color-surface-3)]
data-[selected=true]:ring-2 data-[selected=true]:ring-amber-500/40
hover:bg-[var(--color-surface-4)]
```

### 7.3 Playhead

- 2px 宽 brand-400 + 顶部小三角或圆点  
- `pointer-events-none` 在指示层；拖拽命中区另设  

### 7.4 工具条

- 与 ghost icon 统一高度 32–36  
- 缩放 slider：薄轨 `h-1 rounded-full bg-zinc-700`，thumb brand  

### 7.5 文件

`WorkbenchTimeline.tsx`：只改 className 与外层 wrapper，**不改** pointer 逻辑与 props。

---

## 8. 列表行 List row（分镜）

```txt
flex gap-3 items-center rounded-[var(--radius-md)] px-2 py-2
hover:bg-white/5
data-[active=true]:bg-amber-500/10 data-[active=true]:ring-1 data-[active=true]:ring-amber-500/20
```

左侧 40×40 缩略图 `rounded-md object-cover`；右侧两行：标题 `#n` + caption 旁白截断。

---

## 9. Toast / 引导条

### 9.1 Toast

- 保持现有 Toast 组件；容器建议 `rounded-xl` + soft shadow。  
- 成功/错误图标区不要过大。  
- **减少** info 连发：改造时审计「生成开始」是否可改为舞台内状态。

### 9.2 Banner（配置引导）

```
┌ rounded-xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 ─┐
│ 文案…                                    [去设置] [关闭]          │
└──────────────────────────────────────────────────────────────────┘
```

用于替代侧栏过大状态区的「阻断感」。

---

## 10. 空状态 Empty

```
┌ ui-card 居中 py-12 ──────────────┐
│     [ 插画或 Lucide 大图标 ]      │
│     标题 semibold                 │
│     说明 caption max-w-sm         │
│     [ primary CTA ]               │
└──────────────────────────────────┘
```

场景：无项目、无历史、预览无画面。

---

## 11. 抽屉 Drawer / 模态 Modal

### 11.1 项目设置 Drawer（精修台 BGM 等）

- 右侧宽 360–400  
- 遮罩 `bg-black/50 backdrop-blur-sm`  
- 面板 `surface-2 rounded-l-2xl`  
- 动画：translate-x  

### 11.2 Modal

- 复用 `ConfirmModal`：圆角升至 `rounded-2xl`，按钮走 primary/secondary。

---

## 12. Sticky 底栏（生成台）

```txt
sticky bottom-0 z-20
border-t border-[var(--color-border-subtle)]
bg-[var(--color-surface-1)]/90 backdrop-blur-md
px-4 py-3 flex items-center justify-between gap-3
```

左：上一步 ghost；右：次要 secondary + 主 primary。

---

## 13. 滚动条

保持细滚动条；thumb hover brand（已有）。时间线横向滚动区域同样应用。

---

## 14. 建议新增文件（P1）

```
frontend/src/components/ui/
  Button.tsx
  Input.tsx
  Textarea.tsx
  Card.tsx
  Chip.tsx
  Stepper.tsx
  index.ts
```

P0 可不建文件，只在 `index.css` 增加：

```css
.ui-btn { ... }
.ui-btn-primary { ... }
.ui-btn-secondary { ... }
.ui-input { ... }
.ui-stage { ... }
```

---

## 15. 组件验收 Checklist

- [ ] 全站主 CTA 视觉一致（高度、圆角、颜色）  
- [ ] Input/Select 同高  
- [ ] 卡片 radius ≥ 16px  
- [ ] 时间线在 panel 容器内，无「裸轨道贴边」  
- [ ] 图标按钮均有 aria-label  
- [ ] 无障碍 focus-visible 未被 `outline-none` 单独干掉（需 ring 补偿）  

---

## 16. 对照表：丑点 → 组件药方

| 用户感受 | 原因 | 组件级药方 |
|----------|------|------------|
| 生硬 | 直角+硬边框 | Card/Stage 大圆角 + subtle border |
| 乱 | 按钮变体过多 | 仅 4 variant |
| 挤 | padding 8px | card p-5，区块 gap-6 |
| 看不清主操作 | 主次都描边 | primary 实心 + sticky |
| 工作台像后台 | 多横条工具 | 合并 Topbar + Drawer |
| 字太密 | 10px 说明 | caption 阶梯，删 text-[10px] |