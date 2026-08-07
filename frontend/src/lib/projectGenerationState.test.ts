import { strict as assert } from "node:assert";
import test from "node:test";
import { GenerationRun } from "../types";
import { initialGenerationState, isRunTerminal, reduceRunFetched, reduceRunStarted, shouldRefreshProject } from "./projectGenerationState";

const run = (updatedAt: string, status: GenerationRun["status"] = "running"): GenerationRun => ({
  runId: "r1", projectId: "p", taskId: "t", status, currentSceneId: "s1",
  totalCount: 1, completedCount: 0, skippedCount: 0, failedCount: 0, candidateReviewCount: 0,
  pauseRequested: false, cancelRequested: false, createdAt: updatedAt, updatedAt, items: [],
});

const runWithItem = (updatedAt: string, itemUpdatedAt: string, status: GenerationRun["status"] = "running"): GenerationRun => ({
  ...run(updatedAt, status),
  items: [{ itemId: "i1", sceneId: "s1", position: 0, status: "running_tts", phase: "tts", ttsStatus: "running", imageStatus: "pending", updatedAt: itemUpdatedAt }],
});

test("run reducer starts polling and stops for terminal states", () => {
  const active = reduceRunStarted(initialGenerationState, run("1"));
  assert.equal(active.polling, true);
  assert.equal(reduceRunStarted(active, run("2", "completed")).polling, false);
  assert.equal(isRunTerminal("completed_with_failures"), true);
});

test("identical snapshots do not create state churn", () => {
  const state = reduceRunStarted(initialGenerationState, run("1"));
  assert.equal(reduceRunFetched(state, run("1")), state);
});

test("project refresh follows run status and item timestamps, not run heartbeat", () => {
  assert.equal(shouldRefreshProject(runWithItem("1", "1"), runWithItem("2", "1")), false);
  assert.equal(shouldRefreshProject(runWithItem("1", "1"), runWithItem("2", "2")), true);
  assert.equal(shouldRefreshProject(runWithItem("1", "1", "running"), runWithItem("2", "1", "paused")), true);
});
