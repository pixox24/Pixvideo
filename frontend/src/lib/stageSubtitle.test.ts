import assert from "node:assert/strict";
import test from "node:test";
import {
  buildStageSubtitleModel,
  buildWeightedCues,
  pickActiveCueIndex,
  resolveExportCanvasSize,
  scaleStyleForStage,
} from "./stageSubtitle";

test("buildWeightedCues gives longer text more time", () => {
  const cues = buildWeightedCues(["短", "这是一句很长的旁白内容"], 10);
  assert.equal(cues.length, 2);
  assert.ok(cues[1]!.end - cues[1]!.start > cues[0]!.end - cues[0]!.start);
  assert.equal(cues[0]!.start, 0);
  assert.ok(Math.abs(cues[1]!.end - 10) < 1e-6);
});

test("pickActiveCueIndex keeps last cue during hold (decision 1B)", () => {
  const cues = buildWeightedCues(["第一句", "第二句"], 4);
  assert.equal(pickActiveCueIndex(cues, 0.1, 4), 0);
  assert.equal(pickActiveCueIndex(cues, 3.9, 4), 1);
  // Hold region past audio duration
  assert.equal(pickActiveCueIndex(cues, 4.5, 4, { keepLastDuringHold: true }), 1);
  assert.equal(pickActiveCueIndex(cues, 4.5, 4, { keepLastDuringHold: false }), -1);
});

test("buildStageSubtitleModel hides when subtitles disabled (4A)", () => {
  const model = buildStageSubtitleModel({
    enableSubtitles: false,
    narration: "你好世界",
    localTime: 0.5,
    audioDurationSeconds: 3,
    contentWidth: 360,
    contentHeight: 640,
    mediaWidth: 1440,
    mediaHeight: 2560,
  });
  assert.equal(model.visible, false);
  assert.equal(model.reason, "disabled");
});

test("buildStageSubtitleModel hides without audio duration (2A)", () => {
  const model = buildStageSubtitleModel({
    enableSubtitles: true,
    narration: "你好世界",
    localTime: 0,
    audioDurationSeconds: 0,
    contentWidth: 360,
    contentHeight: 640,
    mediaWidth: 1440,
    mediaHeight: 2560,
  });
  assert.equal(model.visible, false);
  assert.equal(model.reason, "no_audio_duration");
});

test("buildStageSubtitleModel shows cue from real narration", () => {
  const model = buildStageSubtitleModel({
    enableSubtitles: true,
    narration: "背包里只有半瓶水。指南针却疯狂打转。",
    localTime: 0.2,
    audioDurationSeconds: 5,
    style: {
      segmentMode: "sentence",
      maxCharsPerLine: 14,
      maxLines: 2,
      fontSize: 80,
      marginV: 200,
    },
    contentWidth: 360,
    contentHeight: 640,
    mediaWidth: 1440,
    mediaHeight: 2560,
  });
  assert.equal(model.visible, true);
  assert.equal(model.reason, "ok");
  assert.ok(model.activeText.length > 0);
  assert.ok(model.lines.length >= 1);
  assert.ok(model.layout.fontSize > 0);
  assert.ok(model.layout.marginBottom > 0);
});

test("buildStageSubtitleModel keeps last cue in hold region", () => {
  const model = buildStageSubtitleModel({
    enableSubtitles: true,
    narration: "第一句完整表达。第二句继续推进。",
    localTime: 9,
    audioDurationSeconds: 6,
    style: { segmentMode: "sentence", maxCharsPerLine: 20, maxLines: 2 },
    contentWidth: 360,
    contentHeight: 640,
    mediaWidth: 1080,
    mediaHeight: 1920,
  });
  assert.equal(model.visible, true);
  assert.equal(model.inHold, true);
  assert.equal(model.activeCueIndex, model.cues.length - 1);
});

test("scaleStyleForStage uses real export resolution", () => {
  const style = {
    fontSize: 80,
    outlineWidth: 0,
    shadow: 0,
    marginV: 200,
    alignment: 2,
    boxEnabled: true,
    boxPadding: 10,
    boxRadius: 12,
    preset: "caption-box" as const,
  };
  const layout = scaleStyleForStage(style as any, 360, 640, 1440, 2560);
  assert.ok(Math.abs(layout.fontSize - 20) < 0.01); // 80 * (360/1440)
  assert.ok(Math.abs(layout.marginBottom - 50) < 0.01); // 200 * (640/2560)
  assert.equal(layout.textAlign, "center");
  // Export pad_x = max(6, round(10*0.9))=9 → display 9*(360/1440)=2.25
  assert.ok(Math.abs(layout.boxPadX - 2.25) < 0.01);
  // Export pad_y = max(4, round(10*0.55))=6 → display 6*0.25=1.5
  assert.ok(Math.abs(layout.boxPadY - 1.5) < 0.01);
  assert.ok(Math.abs(layout.boxRadius - 3) < 0.01); // 12 * 0.25
});

test("resolveExportCanvasSize reads mediaWidth/Height", () => {
  const size = resolveExportCanvasSize({ mediaWidth: 1440, mediaHeight: 2560 });
  assert.equal(size.width, 1440);
  assert.equal(size.height, 2560);
});
