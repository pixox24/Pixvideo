/** Quick Create wizard steps (PR-C: content → style → voice → review). */
export const WIZARD_STEPS = [
  { id: "content", label: "1. 内容", short: "内容" },
  { id: "style", label: "2. 风格", short: "风格" },
  { id: "voice", label: "3. 声音", short: "声音" },
  { id: "review", label: "4. 确认", short: "确认" },
] as const;

export type WizardStepId = (typeof WIZARD_STEPS)[number]["id"];

export const WIZARD_STEP_HINT: Record<WizardStepId, string> = {
  content: "写好文案与分镜，再进入风格",
  style: "确认画幅、工作流与字幕",
  voice: "确认配音与背景音乐",
  review: "核对后提交生成",
};

/** Stage element ids for scroll-into-view. */
export const WIZARD_STAGE_ID: Record<WizardStepId, string> = {
  content: "stage-content",
  style: "stage-style",
  voice: "stage-voice",
  review: "stage-review",
};
