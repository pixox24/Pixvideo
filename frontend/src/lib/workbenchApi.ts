import { Project, QuickCreateInput, GenerationJob, WorkbenchScene } from "../types";
import { requestJson } from "./api";

export async function createProject(input: QuickCreateInput): Promise<Project> {
  return requestJson<Project>("/api/projects", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: input.title, config: input, scenes: input.scenes.map((scene) => ({ narration: scene.ttsText, visualPrompt: scene.visualPrompt })) }),
  });
}

export const fetchProject = (projectId: string) => requestJson<Project>(`/api/projects/${projectId}`);

export async function patchScene(projectId: string, sceneId: string, patch: Partial<Pick<WorkbenchScene, "narration" | "visualPrompt" | "manualHoldSeconds" | "durationSeconds">>) {
  return requestJson(`/api/projects/${projectId}/scenes/${sceneId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) });
}

export const regenerateImage = (projectId: string, sceneId: string, prompt: string) => requestJson<GenerationJob>(`/api/projects/${projectId}/scenes/${sceneId}/image-generations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt }) });
export const regenerateTts = (projectId: string, sceneId: string, narration: string) => requestJson<GenerationJob>(`/api/projects/${projectId}/scenes/${sceneId}/tts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ narration }) });

export async function uploadSceneAsset(projectId: string, sceneId: string, file: File) {
  const form = new FormData(); form.append("file", file);
  return requestJson(`/api/projects/${projectId}/scenes/${sceneId}/uploads`, { method: "POST", body: form });
}

export const selectAssetVersion = (projectId: string, sceneId: string, versionId: string) => requestJson(`/api/projects/${projectId}/scenes/${sceneId}/versions/${versionId}/select`, { method: "POST" });
export const reorderScenes = (projectId: string, sceneIds: string[]) => requestJson(`/api/projects/${projectId}/scenes/reorder`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sceneIds }) });
export const updateTimeline = (projectId: string, sceneIds: string[], holds: Record<string, number>) => requestJson(`/api/projects/${projectId}/timeline`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sceneIds, holds }) });
export const submitBatchImageGeneration = (projectId: string, sceneIds: string[], promptPrefix = "") => requestJson<GenerationJob[]>(`/api/projects/${projectId}/batch/image-generations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sceneIds, promptPrefix }) });
export const createExport = (projectId: string) => requestJson<GenerationJob>(`/api/projects/${projectId}/exports`, { method: "POST" });
export const cancelWorkbenchJob = (taskId: string) => requestJson(`/api/tasks/${taskId}`, { method: "DELETE" });
