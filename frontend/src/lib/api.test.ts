import assert from "node:assert/strict";
import test from "node:test";
import { mapApiTask, mapHistoryTask, submitVideoTask } from "./api";

test("submitVideoTask clamps subtitle numbers to backend limits", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: any;

  globalThis.fetch = async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ task_id: "task-1" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    await submitVideoTask({
      title: "test",
      scenes: [{ ttsText: "hello" }],
      viewMode: "pure-image",
      subtitleStyle: {
        mode: "ass",
        preset: "short-video-bold",
        fontSize: 300,
        outlineWidth: 3,
        shadow: 0,
        marginV: 120,
        alignment: 2,
        maxCharsPerLine: 14,
        maxLines: 2,
        highlightScale: 125,
        backgroundOpacity: 72,
      },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestBody.subtitle_style.fontSize, 120);
});

test("submitVideoTask renders FastAPI validation details as readable text", async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        detail: [
          {
            type: "less_than_equal",
            loc: ["body", "subtitle_style", "fontSize"],
            msg: "Input should be less than or equal to 120",
            input: 300,
          },
        ],
      }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    );

  try {
    await assert.rejects(
      submitVideoTask({ title: "test", scenes: [{ ttsText: "hello" }] }),
      /subtitle_style\.fontSize: Input should be less than or equal to 120/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("submitVideoTask forwards each scene narration and visual prompt", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: any;

  globalThis.fetch = async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ task_id: "task-scenes" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    await submitVideoTask({
      title: "scene test",
      scenes: [
        { id: 1, ttsText: "first narration", visualPrompt: "first visual" },
        { id: 2, ttsText: "second narration", visualPrompt: "second visual" },
      ],
      viewMode: "pure-image",
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(requestBody.scenes, [
    { narration: "first narration", visual_prompt: "first visual" },
    { narration: "second narration", visual_prompt: "second visual" },
  ]);
});

test("history summaries use n_frames and preserve cancelled status", () => {
  const historyTask = mapHistoryTask({
    task_id: "history-1",
    title: "three scenes",
    status: "cancelled",
    n_frames: 3,
    created_at: "2026-07-13T00:00:00",
  });

  assert.equal(historyTask.sceneCount, 3);
  assert.equal(historyTask.status, "cancelled");
});

test("live task cancellation remains a distinct terminal status", () => {
  const fallback: any = {
    id: "task-1",
    title: "task",
    tabType: "quick-create",
    status: "generating",
    progress: 25,
    currentStep: "rendering",
    sceneCount: 1,
    createdTime: "now",
  };

  const mapped = mapApiTask({ task_id: "task-1", status: "cancelled" }, fallback);

  assert.equal(mapped.status, "cancelled");
});

test("submitVideoTask forwards a stable client request key", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: any;
  globalThis.fetch = async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ task_id: "task-idempotent" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    await submitVideoTask({
      title: "idempotent",
      clientRequestKey: "stable-request-key",
      scenes: [{ ttsText: "hello", visualPrompt: "visual" }],
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requestBody.client_request_key, "stable-request-key");
});
