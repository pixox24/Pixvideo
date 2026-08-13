import { strict as assert } from "node:assert";
import test from "node:test";
import {
  reorderScenes,
  selectAssetVersion,
  getSceneAudioDuration,
  getSceneTimelineDuration,
  getSceneLocalTime,
  buildTimelineLayout,
  getTimelineDuration,
  findSceneAtTime,
  clampTimelineTime,
  formatTimelineTime,
  snapshotFromScenes,
  snapshotsEqual,
  pushTimelineHistory,
  isGaplessSpeechPreview,
  realTimeToGaplessSpeechTime,
  resolveGaplessSpeechPlayback,
} from "./workbenchState";

const project = { projectId: "p", title: "Project", config: {}, scenes: [
  { sceneId: "s1", position: 0, narration: "a", visualPrompt: "", currentVersionId: "v1", durationSeconds: 4, manualHoldSeconds: 0, status: "completed", versions: [] },
  { sceneId: "s2", position: 1, narration: "b", visualPrompt: "", currentVersionId: null, durationSeconds: 3, manualHoldSeconds: 0, status: "pending", versions: [] },
], jobs: [], updatedAt: "now" };

const scene = (sceneId: string, durationSeconds: number, manualHoldSeconds = 0) => ({
  sceneId, position: 0, narration: "", visualPrompt: "", currentVersionId: null,
  durationSeconds, manualHoldSeconds, status: "pending", versions: [],
});

test("reorderScenes rewrites positions without mutating input", () => {
  const input = project.scenes;
  assert.deepEqual(reorderScenes(input, ["s2", "s1"]).map((scene) => scene.sceneId), ["s2", "s1"]);
  assert.equal(input[0].position, 0);
});
test("selectAssetVersion updates only selected scene", () => {
  const next = selectAssetVersion(project, "s2", "v9");
  assert.equal(next.scenes[1].currentVersionId, "v9");
  assert.equal(next.scenes[0].currentVersionId, "v1");
});

test("getSceneAudioDuration subtracts persisted hold from total", () => {
  assert.equal(getSceneAudioDuration(scene("s", 5, 2)), 3);
  assert.equal(getSceneAudioDuration(scene("s", 4, 0)), 4);
  assert.equal(getSceneAudioDuration(scene("s", 0, 0)), 0);
  assert.equal(getSceneAudioDuration(scene("s", 2, 5)), 0);
});

test("getSceneAudioDuration sanitizes NaN and Infinity", () => {
  assert.equal(getSceneAudioDuration(scene("s", NaN, 2)), 0);
  assert.equal(getSceneAudioDuration(scene("s", Infinity, 2)), 0);
  assert.equal(getSceneAudioDuration(scene("s", 5, NaN)), 5);
  assert.equal(getSceneAudioDuration(scene("s", 5, Infinity)), 5);
});

test("getSceneTimelineDuration is audio plus hold without double counting", () => {
  const s = scene("s", 5, 2);
  assert.equal(getSceneTimelineDuration(s), 5);
  assert.equal(getSceneTimelineDuration(s, 0), 3);
  assert.equal(getSceneTimelineDuration(s, 3.5), 6.5);
  assert.equal(getSceneTimelineDuration(s, -1), 3);
});

test("repeated hold edits never accumulate on top of durationSeconds", () => {
  let s = scene("s", 4, 0);
  assert.equal(getSceneTimelineDuration(s), 4);
  s = { ...s, durationSeconds: 6, manualHoldSeconds: 2 };
  assert.equal(getSceneTimelineDuration(s), 6);
  s = { ...s, durationSeconds: 7, manualHoldSeconds: 3 };
  assert.equal(getSceneTimelineDuration(s), 7);
  s = { ...s, durationSeconds: 4, manualHoldSeconds: 0 };
  assert.equal(getSceneTimelineDuration(s), 4);
});

test("empty scenes default to 3 seconds", () => {
  assert.equal(getSceneTimelineDuration(scene("s", 0, 0)), 3);
  assert.equal(getSceneTimelineDuration(scene("s", NaN, NaN)), 3);
});

test("buildTimelineLayout produces contiguous segments and never mutates input", () => {
  const input = [scene("s1", 2), scene("s2", 5, 2), scene("s3", 4)];
  const layout = buildTimelineLayout(input);
  assert.deepEqual(layout.map((item) => [item.startSeconds, item.endSeconds]), [[0, 2], [2, 7], [7, 11]]);
  assert.deepEqual(layout.map((item) => item.audioDurationSeconds), [2, 3, 4]);
  assert.deepEqual(layout.map((item) => item.holdSeconds), [0, 2, 0]);
  assert.equal(input[1].manualHoldSeconds, 2);
  assert.equal(getTimelineDuration(layout), 11);
});

test("buildTimelineLayout applies hold overrides per scene", () => {
  const input = [scene("s1", 2), scene("s2", 5, 2), scene("s3", 4)];
  const layout = buildTimelineLayout(input, { s2: 4 });
  assert.deepEqual(layout.map((item) => item.endSeconds), [2, 9, 13]);
  assert.equal(getTimelineDuration(layout), 13);
});

test("findSceneAtTime uses inclusive start and exclusive end boundaries", () => {
  const layout = buildTimelineLayout([scene("s1", 2), scene("s2", 5, 2), scene("s3", 4)]);
  assert.equal(findSceneAtTime(layout, 0)?.sceneId, "s1");
  assert.equal(findSceneAtTime(layout, 1.999)?.sceneId, "s1");
  assert.equal(findSceneAtTime(layout, 2)?.sceneId, "s2");
  assert.equal(findSceneAtTime(layout, 6.999)?.sceneId, "s2");
  assert.equal(findSceneAtTime(layout, 7)?.sceneId, "s3");
  assert.equal(findSceneAtTime(layout, 10.999)?.sceneId, "s3");
  assert.equal(findSceneAtTime(layout, -5)?.sceneId, "s1");
  assert.equal(findSceneAtTime(layout, NaN)?.sceneId, "s1");
});

test("findSceneAtTime keeps last scene visible at end of project", () => {
  const layout = buildTimelineLayout([scene("s1", 2), scene("s2", 5, 2), scene("s3", 4)]);
  assert.equal(findSceneAtTime(layout, 11)?.sceneId, "s3");
  assert.equal(findSceneAtTime(layout, 50)?.sceneId, "s3");
  assert.equal(findSceneAtTime([], 3), null);
});

test("clampTimelineTime stays within project bounds", () => {
  assert.equal(clampTimelineTime(3.5, 11), 3.5);
  assert.equal(clampTimelineTime(11, 11), 11);
  assert.equal(clampTimelineTime(20, 11), 11);
  assert.equal(clampTimelineTime(-1, 11), 0);
  assert.equal(clampTimelineTime(NaN, 11), 0);
  assert.equal(clampTimelineTime(Infinity, 11), 11);
});

test("formatTimelineTime renders MM:SS.cc", () => {
  assert.equal(formatTimelineTime(0), "00:00.00");
  assert.equal(formatTimelineTime(1.5), "00:01.50");
  assert.equal(formatTimelineTime(61.05), "01:01.05");
  assert.equal(formatTimelineTime(-3), "00:00.00");
  assert.equal(formatTimelineTime(NaN), "00:00.00");
  assert.equal(formatTimelineTime(599.99), "09:59.99");
});

test("buildTimelineLayout with reordered scenes follows the new order", () => {
  const layout = buildTimelineLayout([scene("s2", 5, 2), scene("s1", 2), scene("s3", 4)]);
  assert.deepEqual(layout.map((item) => item.sceneId), ["s2", "s1", "s3"]);
  assert.deepEqual(layout.map((item) => item.startSeconds), [0, 5, 7]);
  assert.equal(getTimelineDuration(layout), 11);
});

test("hundred scene layout builds and finds quickly", () => {
  const scenes = Array.from({ length: 100 }, (_, index) => scene(`s${index}`, 3));
  const layout = buildTimelineLayout(scenes);
  assert.equal(getTimelineDuration(layout), 300);
  assert.equal(findSceneAtTime(layout, 297)?.sceneId, "s99");
});

test("phase2 scenario: 2s + 3s audio with 2s hold + 4s totals 11 seconds", () => {
  const scenes = [scene("s1", 2), scene("s2", 5, 2), scene("s3", 4)];
  const layout = buildTimelineLayout(scenes);
  assert.equal(getTimelineDuration(layout), 11);
  assert.deepEqual(layout.map((item) => item.audioDurationSeconds), [2, 3, 4]);
  assert.equal(findSceneAtTime(layout, 2)?.sceneId, "s2");
  assert.equal(findSceneAtTime(layout, 7)?.sceneId, "s3");
});

test("phase2 scenario: hold region keeps image visible and audio region ends at 5s", () => {
  const layout = buildTimelineLayout([scene("s1", 2), scene("s2", 5, 2), scene("s3", 4)]);
  const s2 = layout[1];
  for (let t = 5; t < 7; t += 0.5) {
    assert.equal(findSceneAtTime(layout, t)?.sceneId, "s2");
    assert.equal(getSceneLocalTime(s2, t) >= s2.audioDurationSeconds, true);
  }
  assert.equal(findSceneAtTime(layout, 5)?.sceneId, "s2");
  assert.equal(getSceneLocalTime(s2, 5) >= s2.audioDurationSeconds, true);
});

test("phase2 scenario: seek to 3.5s starts scene 2 narration at 1.5s", () => {
  const layout = buildTimelineLayout([scene("s1", 2), scene("s2", 5, 2), scene("s3", 4)]);
  const item = findSceneAtTime(layout, 3.5)!;
  assert.equal(item.sceneId, "s2");
  assert.ok(Math.abs(getSceneLocalTime(item, 3.5) - 1.5) < 1e-9);
});

test("phase2 scenario: seek to 8s starts scene 3 narration at 1s", () => {
  const layout = buildTimelineLayout([scene("s1", 2), scene("s2", 5, 2), scene("s3", 4)]);
  const item = findSceneAtTime(layout, 8)!;
  assert.equal(item.sceneId, "s3");
  assert.ok(Math.abs(getSceneLocalTime(item, 8) - 1) < 1e-9);
});

test("phase2 scenario: playback ends exactly at total duration", () => {
  const layout = buildTimelineLayout([scene("s1", 2), scene("s2", 5, 2), scene("s3", 4)]);
  const clamped = clampTimelineTime(11.4, getTimelineDuration(layout));
  assert.equal(clamped, 11);
  assert.equal(findSceneAtTime(layout, clamped)?.sceneId, "s3");
});

test("phase2 scenario: segments never overlap so two narrations can never play at once", () => {
  const layout = buildTimelineLayout([scene("s1", 2), scene("s2", 5, 2), scene("s3", 4)]);
  for (let index = 1; index < layout.length; index += 1) {
    assert.equal(layout[index].startSeconds, layout[index - 1].endSeconds);
  }
});

test("snapshotFromScenes captures order and holds", () => {
  const snapshot = snapshotFromScenes([scene("s1", 2, 1), scene("s2", 5, 2)]);
  assert.deepEqual(snapshot.sceneIds, ["s1", "s2"]);
  assert.deepEqual(snapshot.holds, { s1: 1, s2: 2 });
  assert.equal(snapshotFromScenes([scene("s3", 3, NaN)]).holds.s3, 0);
  assert.equal(snapshotFromScenes([scene("s4", 3, -2)]).holds.s4, 0);
});

test("snapshotsEqual compares order and holds", () => {
  const left = snapshotFromScenes([scene("s1", 2, 1), scene("s2", 5, 2)]);
  assert.equal(snapshotsEqual(left, snapshotFromScenes([scene("s1", 2, 1), scene("s2", 5, 2)])), true);
  assert.equal(snapshotsEqual(left, snapshotFromScenes([scene("s2", 2, 1), scene("s1", 5, 2)])), false);
  assert.equal(snapshotsEqual(left, snapshotFromScenes([scene("s1", 2, 0), scene("s2", 5, 2)])), false);
});

test("pushTimelineHistory pushes previous present and clears future", () => {
  const a = snapshotFromScenes([scene("s1", 2), scene("s2", 3)]);
  const b = snapshotFromScenes([scene("s2", 3), scene("s1", 2)]);
  const c = snapshotFromScenes([scene("s1", 2), scene("s2", 5, 2)]);
  const first = pushTimelineHistory([], a, b);
  assert.deepEqual(first.past, [a]);
  assert.deepEqual(first.present, b);
  assert.deepEqual(first.future, []);
  const second = pushTimelineHistory(first.past, b, c);
  assert.deepEqual(second.past, [a, b]);
  assert.deepEqual(second.present, c);
});

test("pushTimelineHistory no-ops on identical snapshot", () => {
  const a = snapshotFromScenes([scene("s1", 2), scene("s2", 3)]);
  const result = pushTimelineHistory([{ sceneIds: ["x"], holds: {} }], a, snapshotFromScenes([scene("s1", 2), scene("s2", 3)]));
  assert.deepEqual(result.past, [{ sceneIds: ["x"], holds: {} }]);
  assert.deepEqual(result.present, a);
});

test("pushTimelineHistory respects the history limit", () => {
  const a = snapshotFromScenes([scene("s1", 1)]);
  const b = snapshotFromScenes([scene("s1", 1, 1)]);
  const c = snapshotFromScenes([scene("s1", 1, 2)]);
  let past: typeof a[] = [];
  let present = a;
  past = pushTimelineHistory(past, present, b).past;
  past = pushTimelineHistory(past, b, c).past;
  assert.equal(past.length, 2);
  const many = Array.from({ length: 30 }, (_, index) => snapshotFromScenes([scene("s1", 1, index)]));
  let smallPast: typeof a[] = [];
  let smallPresent = a;
  for (const next of many) {
    const result = pushTimelineHistory(smallPast, smallPresent, next);
    smallPast = result.past;
    smallPresent = result.present;
  }
  assert.equal(smallPast.length, 20);
});

test("isGaplessSpeechPreview defaults continuous true, per_scene false", () => {
  assert.equal(isGaplessSpeechPreview({}), true);
  assert.equal(isGaplessSpeechPreview({ ttsDelivery: "continuous" }), true);
  assert.equal(isGaplessSpeechPreview({ ttsDelivery: "per_scene" }), false);
  assert.equal(isGaplessSpeechPreview({ tts_delivery: "sequential" }), false);
});

test("gapless speech continues into next scene during hold", () => {
  // scene0: audio 5 + hold 2 = 7; scene1: audio 4 + hold 0 = 4
  const layout = buildTimelineLayout([
    scene("s0", 7, 2),
    scene("s1", 4, 0),
  ]);
  // At t=5.5 (in s0 hold): speech should already be into s1 at ~0.5s
  const speechT = realTimeToGaplessSpeechTime(layout, 5.5);
  assert.ok(Math.abs(speechT - 5.5) < 1e-6);
  const play = resolveGaplessSpeechPlayback(layout, 5.5);
  assert.ok(play);
  assert.equal(play!.sceneId, "s1");
  assert.ok(Math.abs(play!.localTime - 0.5) < 1e-6);
  assert.equal(play!.playing, true);

  // At t=3 (still s0 speech): play s0 at 3s
  const mid = resolveGaplessSpeechPlayback(layout, 3);
  assert.equal(mid!.sceneId, "s0");
  assert.ok(Math.abs(mid!.localTime - 3) < 1e-6);
});
