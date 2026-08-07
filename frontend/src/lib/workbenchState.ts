import { Project, WorkbenchScene } from "../types";

export function reorderScenes(scenes: WorkbenchScene[], sceneIds: string[]): WorkbenchScene[] {
  const byId = new Map(scenes.map((scene) => [scene.sceneId, scene]));
  return sceneIds.map((sceneId, position) => ({ ...byId.get(sceneId)!, position }));
}

export function clampManualHold(audioSeconds: number, requestedHold: number): number {
  void audioSeconds;
  return Math.max(0, Number.isFinite(requestedHold) ? requestedHold : 0);
}

export function selectAssetVersion(project: Project, sceneId: string, versionId: string): Project {
  return {
    ...project,
    scenes: project.scenes.map((scene) =>
      scene.sceneId === sceneId ? { ...scene, currentVersionId: versionId } : scene,
    ),
  };
}

