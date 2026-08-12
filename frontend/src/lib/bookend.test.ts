import assert from "node:assert/strict";
import test from "node:test";
import {
  getBookendPlaybackState,
  getPlaybackTotalDuration,
  normalizeBookendConfig,
} from "./bookend";

test("normalize defaults enabled", () => {
  const cfg = normalizeBookendConfig({});
  assert.equal(cfg.enabled, true);
  assert.equal(cfg.introSeconds, 1.2);
  assert.equal(cfg.outroSeconds, 2.0);
});

test("playback total includes bookends", () => {
  const cfg = normalizeBookendConfig({});
  assert.equal(getPlaybackTotalDuration(10, cfg), 13.2);
});

test("intro has no narration and rising opacity", () => {
  const cfg = normalizeBookendConfig({});
  const mid = getBookendPlaybackState(0.3, 10, cfg);
  assert.equal(mid.phase, "intro");
  assert.equal(mid.narrationEnabled, false);
  assert.ok(mid.pictureOpacity > 0 && mid.pictureOpacity <= 1);
});

test("outro disables narration", () => {
  const cfg = normalizeBookendConfig({});
  const state = getBookendPlaybackState(12.5, 10, cfg); // after content+intro
  assert.equal(state.phase, "outro");
  assert.equal(state.narrationEnabled, false);
});
