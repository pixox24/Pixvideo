# Custom Select Component Design

## Goal

Replace every native frontend `<select>` control with a shared custom dropdown that matches PixVideo's dark interface and provides consistent interaction across the application.

## Chosen approach

Implement a lightweight, dependency-free React `Select` component. It will use the project's existing Tailwind styling and Lucide icon set instead of adding a UI library.

## Component contract

The component will accept:

- `value`, `onChange`, and an `options` list of `{ value, label, disabled? }` entries.
- `placeholder`, `disabled`, `className`, and optional sizing/label support where needed.
- The existing call sites' values and change handlers so no business behavior changes.

## Visual design

- A dark, rounded trigger with a subtle border, inset depth, and a chevron indicator.
- Amber focus ring and selected-state accent using the existing brand colors.
- A floating, dark menu with restrained shadow and a slim border.
- Hovered options receive a soft contrast lift; the selected option shows an amber check icon.
- Disabled controls and options remain visibly distinct.

## Interaction and accessibility

- Open through pointer or keyboard interaction.
- Close on outside click, Escape, selection, or focus loss.
- Support Arrow Up/Down to navigate, Enter/Space to select or open, and Escape to close.
- Use appropriate button/listbox/option semantics and return focus to the trigger after closing.

## Rollout

1. Add the shared component under `frontend/src/components`.
2. Replace every native `<select>` in the frontend source while preserving each control's state and options.
3. Verify dropdown behavior manually and run the TypeScript build checks.
