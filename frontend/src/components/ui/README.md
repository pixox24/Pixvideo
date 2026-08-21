# UI foundation (PR-A)

Global design tokens and utility classes live in:

- `frontend/src/index.css`

Spec documents:

- `docs/ux-ui-redesign/01-design-principles.md`
- `docs/ux-ui-redesign/03-component-spec.md`
- `docs/ux-ui-redesign/04-implementation-plan.md` (PR-A section)

## Available classes (PR-A)

| Class | Role |
|-------|------|
| `.ui-card` | Main content card |
| `.ui-panel` | Nested / recessed panel |
| `.ui-stage` | Video / image preview stage |
| `.ui-btn` + `.ui-btn-primary` / `secondary` / `ghost` / `outline` / `danger` | Buttons |
| `.ui-btn-sm` / `.ui-btn-lg` / `.ui-btn-icon` | Button sizes |
| `.ui-input` / `.ui-input-error` | Text inputs & textareas |
| `.ui-chip` + semantic modifiers | Status pills |
| `.ui-sticky-footer` | Create-flow sticky bar shell |
| `.ui-segment` | Segmented control (`aria-pressed`) |
| `.text-label` / `.text-caption` | Type helpers |

## Usage

```html
<button type="button" class="ui-btn ui-btn-primary">生成项目</button>
<input class="ui-input" placeholder="主题" />
<div class="ui-card">…</div>
```

Combine modifiers: `class="ui-btn ui-btn-primary ui-btn-lg"`.

React components under this folder (Button.tsx, etc.) may be added in **PR-G**; until then prefer these CSS classes or Tailwind aligned to the same tokens.
