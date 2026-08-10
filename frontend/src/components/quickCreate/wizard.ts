/** Quick Create 3-step wizard definition (Batch B). */
export const WIZARD_STEPS = [
  { id: "content", label: "1. 内容", short: "内容" },
  { id: "production", label: "2. 成片设定", short: "设定" },
  { id: "review", label: "3. 核对生成", short: "生成" },
] as const;

export type WizardStepId = (typeof WIZARD_STEPS)[number]["id"];
