import { GenerationRun, GenerationRunStatus } from "../types";

export interface ProjectGenerationState {
  run: GenerationRun | null;
  polling: boolean;
  lastProjectUpdatedAt: string | null;
  error: unknown;
  actionBusy: string | null;
}

export const initialGenerationState: ProjectGenerationState = {
  run: null,
  polling: false,
  lastProjectUpdatedAt: null,
  error: null,
  actionBusy: null,
};

export const isRunTerminal = (status?: GenerationRunStatus | null) =>
  status === "completed" || status === "completed_with_failures" || status === "cancelled" || status === "failed";

export function reduceRunStarted(state: ProjectGenerationState, run: GenerationRun): ProjectGenerationState {
  return { ...state, run, polling: !isRunTerminal(run.status), error: null };
}

export function reduceRunFetched(state: ProjectGenerationState, run: GenerationRun): ProjectGenerationState {
  if (state.run && state.run.runId === run.runId && state.run.updatedAt === run.updatedAt) return state;
  return { ...state, run, polling: !isRunTerminal(run.status), error: null };
}

export function reduceRunActionStarted(state: ProjectGenerationState, action: string): ProjectGenerationState {
  return { ...state, actionBusy: action, error: null };
}

export function reduceRunActionFailed(state: ProjectGenerationState, error: unknown): ProjectGenerationState {
  return { ...state, actionBusy: null, error };
}

export function reduceRunActionFinished(state: ProjectGenerationState, run: GenerationRun): ProjectGenerationState {
  return { ...state, run, actionBusy: null, polling: !isRunTerminal(run.status), error: null };
}

export function shouldRefreshProject(previous: GenerationRun | null, next: GenerationRun): boolean {
  return !previous || previous.updatedAt !== next.updatedAt || previous.items.some((item, index) => item.updatedAt !== next.items[index]?.updatedAt);
}
