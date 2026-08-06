import assert from "node:assert/strict";
import test from "node:test";
import {
  segmentPreviewText,
  scaleStyleForPreview,
  splitPreviewHighlights,
  stripDisplayPunctuation,
  wrapPreviewText,
} from "./subtitlePreview";
import { SubtitleStyle } from "../types";

const style: SubtitleStyle = {
  mode: "ass",
  preset: "short-video-bold",
  fontSize: 52,
  primaryColor: "#FFFFFF",
  accentColor: "#FFD43B",
  outlineColor: "#000000",
  backColor: "#000000",
  outlineWidth: 3,
  shadow: 0,
  marginV: 120,
  alignment: 2,
  maxCharsPerLine: 4,
  maxLines: 2,
  animation: "fade",
  segmentMode: "sentence",
};

test("wrapPreviewText honors its line limit", () => {
  assert.deepEqual(wrapPreviewText("一二三四五六七八九", 4, 2), ["一二三四", "五六七…"]);
});

test("stripDisplayPunctuation removes terminal punctuation", () => {
  assert.equal(stripDisplayPunctuation("你好。"), "你好");
  assert.equal(stripDisplayPunctuation("再见！"), "再见");
});

test("sentence mode splits on commas and periods without hard cutting", () => {
  assert.deepEqual(
    segmentPreviewText("有人说，AI会取代人类。取代不了深夜那碗面的温度。", "sentence", style),
    ["有人说", "AI会取代人类", "取代不了深夜那碗面的温度"],
  );
});

test("portrait preview preserves a usable subtitle size", () => {
  const scaled = scaleStyleForPreview(style, "portrait");
  assert.ok(scaled.fontSize >= 12);
  assert.ok(scaled.marginBottom > 0);
});

test("splitPreviewHighlights keeps manual phrases intact and supports keyword colors", () => {
  assert.deepEqual(
    splitPreviewHighlights("让表达力成为重点", ["", "表达力", "重点"], { 表达力: "#FF0000" }, "#FFD43B"),
    [
      { text: "让", highlighted: false, color: undefined },
      { text: "表达力", highlighted: true, color: "#FF0000" },
      { text: "成为", highlighted: false, color: undefined },
      { text: "重点", highlighted: true, color: "#FFD43B" },
    ],
  );
});
