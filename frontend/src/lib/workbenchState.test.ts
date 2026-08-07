import { strict as assert } from "node:assert";
import test from "node:test";
import { reorderScenes, selectAssetVersion, clampManualHold } from "./workbenchState";

const project = { projectId: "p", title: "Project", config: {}, scenes: [
  { sceneId: "s1", position: 0, narration: "a", visualPrompt: "", currentVersionId: "v1", durationSeconds: 4, manualHoldSeconds: 0, status: "completed", versions: [] },
  { sceneId: "s2", position: 1, narration: "b", visualPrompt: "", currentVersionId: null, durationSeconds: 3, manualHoldSeconds: 0, status: "pending", versions: [] },
], jobs: [], updatedAt: "now" };

test("reorderScenes rewrites positions without mutating input", () => {
  const input = project.scenes;
  assert.deepEqual(reorderScenes(input, ["s2", "s1"]).map((scene) => scene.sceneId), ["s2", "s1"]);
  assert.equal(input[0].position, 0);
});
test("manual hold is never negative", () => assert.equal(clampManualHold(4.2, -1), 0));
test("selectAssetVersion updates only selected scene", () => {
  const next = selectAssetVersion(project, "s2", "v9");
  assert.equal(next.scenes[1].currentVersionId, "v9");
  assert.equal(next.scenes[0].currentVersionId, "v1");
});
