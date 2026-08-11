import assert from "node:assert/strict";
import test from "node:test";
import {
  buildStoryboardNarrations,
  packSemanticUnits,
  softExpandByPause,
  splitDraftByRule,
  suggestSceneCount,
} from "./storyboardSplit";

const SAMPLE =
  "三十五岁不是人生的分水岭，而是你终于开始为自己活的那个起点。身边人都在交卷，你却还在思考题目，这恰恰说明你比他们更认真。荣格说中年是第二次成年，前半生为别人活，后半生该找回真正的自己。别拿别人的进度条来丈量自己的人生，每个人的花期本来就不一样。";

test("sentence split respects terminal punctuation", () => {
  const units = splitDraftByRule(SAMPLE, "sentence");
  assert.ok(units.length >= 3);
  assert.ok(units.some((u) => u.includes("后半生该找回真正的自己")));
  assert.ok(!units.some((u) => u === "后半生该" || u === "找回真正的自己"));
});

test("soft expand splits long pause-joined clauses", () => {
  const expanded = softExpandByPause(["荣格说中年是第二次成年，前半生为别人活，后半生该找回真正的自己。"]);
  assert.deepEqual(expanded, [
    "荣格说中年是第二次成年",
    "前半生为别人活",
    "后半生该找回真正的自己。",
  ]);
});

test("soft expand does not break short pause fragments", () => {
  assert.deepEqual(softExpandByPause(["是，否"]), ["是，否"]);
});

test("pack never character-slices when units are fewer than target", () => {
  const units = [
    "荣格说中年是第二次成年",
    "前半生为别人活",
    "后半生该找回真正的自己",
  ];
  const packed = packSemanticUnits(units, 6);
  assert.deepEqual(packed, units);
  assert.ok(!packed.some((u) => u === "后半生该"));
  assert.ok(packed.includes("后半生该找回真正的自己"));
});

test("pack merges when units exceed target", () => {
  const units = ["一。", "二。", "三。", "四。", "五。", "六。"];
  const packed = packSemanticUnits(units, 3);
  assert.equal(packed.length, 3);
  assert.equal(packed.join(""), units.join(""));
});

test("buildStoryboardNarrations with forced high target keeps phrase intact", () => {
  const text = "荣格说中年是第二次成年，前半生为别人活，后半生该找回真正的自己。";
  const scenes = buildStoryboardNarrations(text, "sentence", 6);
  assert.ok(scenes.every((s) => !s.startsWith("找回真正") || s.includes("后半生")));
  assert.ok(scenes.some((s) => s.includes("后半生该找回真正的自己") || s === "后半生该找回真正的自己"));
  // Must not produce the classic hard-cut pair from equal char packing.
  assert.ok(!scenes.includes("后半生该"));
  assert.ok(!scenes.some((s) => s === "找回真正的自己" && !scenes.some((x) => x.includes("后半生"))));
});

test("suggestSceneCount follows semantic units after soft expand", () => {
  const text = "荣格说中年是第二次成年，前半生为别人活，后半生该找回真正的自己。";
  const n = suggestSceneCount(text, "sentence");
  assert.equal(n, 3);
});
