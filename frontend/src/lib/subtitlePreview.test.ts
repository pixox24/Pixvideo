import assert from "node:assert/strict";
import test from "node:test";
import { segmentPreviewText, scaleStyleForPreview, splitPreviewHighlights, wrapPreviewText } from "./subtitlePreview";
import { SubtitleStyle } from "../types";

const style: SubtitleStyle = {
  mode: "ass", preset: "short-video-bold", fontSize: 52, primaryColor: "#FFFFFF", accentColor: "#FFD43B", outlineColor: "#000000", backColor: "#000000", outlineWidth: 3, shadow: 0, marginV: 120, alignment: 2, maxCharsPerLine: 4, maxLines: 2, animation: "fade", segmentMode: "phrase",
};

test("wrapPreviewText honors its line limit", () => {
  assert.deepEqual(wrapPreviewText("一二三四五六七八九", 4, 2), ["一二三四", "五六七…"]);
});

test("segmentPreviewText supports every configured mode", () => {
  assert.equal(segmentPreviewText("你好。再见！", "sentence", style).length, 2);
  assert.deepEqual(segmentPreviewText("一二三四五", "line", style), ["一二三四", "五"]);
  assert.equal(segmentPreviewText("一二三四五六七", "phrase", style).length, 2);
});

test("portrait preview preserves a usable subtitle size", () => {
  const scaled = scaleStyleForPreview(style, "portrait");
  assert.ok(scaled.fontSize >= 12);
  assert.ok(scaled.marginBottom > 0);
});

test("splitPreviewHighlights keeps manual phrases intact and ignores empty values", () => {
  assert.deepEqual(
    splitPreviewHighlights("让表达力成为重点", ["", "表达力", "重点"]),
    [
      { text: "让", highlighted: false },
      { text: "表达力", highlighted: true },
      { text: "成为", highlighted: false },
      { text: "重点", highlighted: true },
    ],
  );
});
