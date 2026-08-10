const FIRST_RUN_COACH_KEY = "pixvideo.onboarding.coach.v1";
const CREATE_TIP_KEY = "pixvideo.onboarding.create-tip.v1";
const WORKBENCH_KEYS_TIP_KEY = "pixvideo.onboarding.workbench-keys.v1";

export type CoachDismissState = {
  dismissedAt: string;
  version: 1;
};

function readFlag(key: string): boolean {
  try {
    return Boolean(localStorage.getItem(key));
  } catch {
    return false;
  }
}

function writeFlag(key: string) {
  try {
    localStorage.setItem(
      key,
      JSON.stringify({ dismissedAt: new Date().toISOString(), version: 1 } satisfies CoachDismissState),
    );
  } catch {
    /* ignore quota */
  }
}

export const isFirstRunCoachDismissed = () => readFlag(FIRST_RUN_COACH_KEY);
export const dismissFirstRunCoach = () => writeFlag(FIRST_RUN_COACH_KEY);

export const isCreateTipDismissed = () => readFlag(CREATE_TIP_KEY);
export const dismissCreateTip = () => writeFlag(CREATE_TIP_KEY);

export const isWorkbenchKeysTipDismissed = () => readFlag(WORKBENCH_KEYS_TIP_KEY);
export const dismissWorkbenchKeysTip = () => writeFlag(WORKBENCH_KEYS_TIP_KEY);
