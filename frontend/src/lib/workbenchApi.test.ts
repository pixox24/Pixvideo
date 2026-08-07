import { strict as assert } from "node:assert";
import test from "node:test";
import { createProject } from "./workbenchApi";

test("createProject maps Quick Create scenes to API contract", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async (_input, init) => {
    const payload = JSON.parse(String(init?.body));
    assert.equal(payload.scenes[0].narration, "hello");
    assert.equal(payload.scenes[0].visualPrompt, "scene");
    return new Response(JSON.stringify({ projectId: "p" }), { status: 201 });
  }) as typeof fetch;
  await createProject({ title: "x", scenes: [{ ttsText: "hello", visualPrompt: "scene" }] });
  globalThis.fetch = original;
});

