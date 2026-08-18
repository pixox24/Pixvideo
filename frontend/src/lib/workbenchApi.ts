import { Project, QuickCreateInput, ExportSubmission, GenerationJob, WorkbenchScene, GenerationRun } from "../types";
import { requestJson } from "./api";

export async function createProject(input: QuickCreateInput): Promise<Project> {
  return requestJson<Project>("/api/projects", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: input.title,
      config: input,
      scenes: input.scenes.map((scene) => ({
        narration: scene.ttsText,
        visualPrompt: scene.visualPrompt,
        visualFocus: scene.visualFocus,
        textAnchors: scene.textAnchors,
        lockedFields: scene.lockedFields,
        editedFields: scene.editedFields,
        locked: scene.locked,
      })),
    }),
  });
}

export const fetchProject = (projectId: string) => requestJson<Project>(`/api/projects/${projectId}`);
export const patchProject = (projectId: string, body: { title?: string; config?: Record<string, unknown>; expectedUpdatedAt?: string }) => requestJson<Project>(`/api/projects/${projectId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const createProjectFromHistory = (taskId: string) => requestJson<Project>(`/api/projects/from-history/${taskId}`, { method: "POST" });

export async function patchScene(projectId: string, sceneId: string, patch: Partial<Pick<WorkbenchScene, "narration" | "visualPrompt" | "visualFocus" | "textAnchors" | "lockedFields" | "editedFields" | "locked" | "manualHoldSeconds" | "durationSeconds">>) {
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
export const submitBatchImageGeneration = (projectId: string, sceneIds: string[], promptPrefix = "") => requestJson<{ jobs: GenerationJob[] }>(`/api/projects/${projectId}/batch/image-generations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sceneIds, promptPrefix }) });
export const createExport = (projectId: string, allowIncomplete = false) => requestJson<ExportSubmission>(`/api/projects/${projectId}/exports`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ allowIncomplete }) });
export const retryExport = (projectId: string, exportId: string) => requestJson<ExportSubmission>(`/api/projects/${projectId}/exports/${exportId}/retry`, { method: "POST" });
export const cancelExport = (projectId: string, exportId: string) =>
  requestJson<{ exportId: string; status: string }>(`/api/projects/${projectId}/exports/${exportId}/cancel`, {
    method: "POST",
  });
export const cancelWorkbenchJob = (taskId: string) => requestJson(`/api/tasks/${taskId}`, { method: "DELETE" });

export const startGenerationRun = (projectId: string, sceneIds?: string[], configOverride?: Record<string, unknown>) => requestJson<GenerationRun>(`/api/projects/${projectId}/generation-runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sceneIds, configOverride }) });
export const fetchGenerationRun = (projectId: string, runId: string) => requestJson<GenerationRun>(`/api/projects/${projectId}/generation-runs/${runId}`);
export const fetchActiveGenerationRun = (projectId: string) => requestJson<GenerationRun | null>(`/api/projects/${projectId}/generation-runs/active`);
const runAction = (projectId: string, runId: string, action: string) => requestJson<GenerationRun>(`/api/projects/${projectId}/generation-runs/${runId}/${action}`, { method: "POST" });
export const pauseGenerationRun = (projectId: string, runId: string) => runAction(projectId, runId, "pause");
export const resumeGenerationRun = (projectId: string, runId: string) => runAction(projectId, runId, "resume");
export const cancelGenerationRun = (projectId: string, runId: string) => runAction(projectId, runId, "cancel");
export const retryFailedGeneration = (projectId: string, runId: string) => runAction(projectId, runId, "retry-failed");
