import { Project, WorkbenchScene } from "../types";

const DEFAULT_EMPTY_SCENE_SECONDS = 3;

function toFiniteSeconds(value: number): number {
  return Number.isFinite(value) ? value : 0;
}

function clampNonNegative(value: number): number {
  return Math.max(0, toFiniteSeconds(value));
}

export function reorderScenes(scenes: WorkbenchScene[], sceneIds: string[]): WorkbenchScene[] {
  const byId = new Map(scenes.map((scene) => [scene.sceneId, scene]));
  return sceneIds.map((sceneId, position) => ({ ...byId.get(sceneId)!, position }));
}

/**
 * Audio duration derived from persisted values.
 * Contract: durationSeconds = audioDurationSeconds + manualHoldSeconds,
 * so the audio part is always computed from the server-confirmed total minus hold.
 */
export function getSceneAudioDuration(scene: Pick<WorkbenchScene, "durationSeconds" | "manualHoldSeconds">): number {
  const duration = toFiniteSeconds(scene.durationSeconds);
  const hold = clampNonNegative(scene.manualHoldSeconds);
  return clampNonNegative(duration - hold);
}

/**
 * Total timeline duration for one scene.
 * `holdOverride` is used during local dragging; it must NOT be applied on top of
 * a durationSeconds that already includes the persisted hold.
 * Scenes with no audio and no hold fall back to a fixed default so the timeline
 * never collapses.
 */
export function getSceneTimelineDuration(
  scene: Pick<WorkbenchScene, "durationSeconds" | "manualHoldSeconds">,
  holdOverride?: number,
): number {
  const audio = getSceneAudioDuration(scene);
  const hold = clampNonNegative(holdOverride ?? scene.manualHoldSeconds);
  const duration = audio + hold;
  return duration > 0 ? duration : DEFAULT_EMPTY_SCENE_SECONDS;
}

export interface TimelineLayoutItem {
  sceneId: string;
  index: number;
  startSeconds: number;
  endSeconds: number;
  durationSeconds: number;
  audioDurationSeconds: number;
  holdSeconds: number;
}

/**
 * Build the contiguous single-track layout. Segment start is inclusive,
 * segment end is exclusive: [start, end).
 * Never mutates the input scenes.
 */
export function buildTimelineLayout(scenes: WorkbenchScene[], holds?: Record<string, number>): TimelineLayoutItem[] {
  let cursor = 0;
  return scenes.map((scene, index) => {
    const hold = clampNonNegative(holds?.[scene.sceneId] ?? scene.manualHoldSeconds);
    const duration = getSceneTimelineDuration(scene, hold);
    const item: TimelineLayoutItem = {
      sceneId: scene.sceneId,
      index,
      startSeconds: cursor,
      endSeconds: cursor + duration,
      durationSeconds: duration,
      audioDurationSeconds: getSceneAudioDuration(scene),
      holdSeconds: hold,
    };
    cursor += duration;
    return item;
  });
}

export function getTimelineDuration(layout: TimelineLayoutItem[]): number {
  const last = layout[layout.length - 1];
  return last ? last.endSeconds : 0;
}

/**
 * Scene containing the given time. When time equals the project end,
 * the last scene is still returned so its image keeps displaying.
 */
export function findSceneAtTime(layout: TimelineLayoutItem[], currentTime: number): TimelineLayoutItem | null {
  if (layout.length === 0) return null;
  const time = clampNonNegative(currentTime);
  for (const item of layout) {
    if (time < item.endSeconds) return item;
  }
  return layout[layout.length - 1];
}

export function clampTimelineTime(currentTime: number, totalDuration: number): number {
  const total = clampNonNegative(totalDuration);
  if (currentTime === Infinity) return total;
  return Math.min(clampNonNegative(currentTime), total);
}

/** Offset of currentTime inside the segment containing the item. */
export function getSceneLocalTime(item: TimelineLayoutItem, currentTime: number): number {
  return Math.max(0, clampNonNegative(currentTime) - item.startSeconds);
}

export function formatTimelineTime(seconds: number): string {
  const totalCentiseconds = Math.floor(clampNonNegative(seconds) * 100);
  const minutes = Math.floor(totalCentiseconds / 6000);
  const remaining = totalCentiseconds % 6000;
  const wholeSeconds = Math.floor(remaining / 100);
  const centiseconds = remaining % 100;
  return `${String(minutes).padStart(2, "0")}:${String(wholeSeconds).padStart(2, "0")}.${String(centiseconds).padStart(2, "0")}`;
}

export function selectAssetVersion(project: Project, sceneId: string, versionId: string): Project {
  return {
    ...project,
    scenes: project.scenes.map((scene) =>
      scene.sceneId === sceneId ? { ...scene, currentVersionId: versionId } : scene,
    ),
  };
}

export interface TimelineSnapshot {
  sceneIds: string[];
  holds: Record<string, number>;
}

export function snapshotFromScenes(scenes: WorkbenchScene[]): TimelineSnapshot {
  return {
    sceneIds: scenes.map((scene) => scene.sceneId),
    holds: Object.fromEntries(scenes.map((scene) => [scene.sceneId, clampNonNegative(scene.manualHoldSeconds)])),
  };
}

export function snapshotsEqual(left: TimelineSnapshot, right: TimelineSnapshot): boolean {
  if (left.sceneIds.length !== right.sceneIds.length) return false;
  for (let index = 0; index < left.sceneIds.length; index += 1) {
    if (left.sceneIds[index] !== right.sceneIds[index]) return false;
  }
  const leftKeys = Object.keys(left.holds);
  const rightKeys = Object.keys(right.holds);
  if (leftKeys.length !== rightKeys.length) return false;
  for (const key of leftKeys) {
    if (left.holds[key] !== right.holds[key]) return false;
  }
  return true;
}

/**
 * Records a timeline edit into the undo stack. Returns an empty future because
 * a new edit invalidates any redo history. No-op when the edit equals present.
 */
export function pushTimelineHistory(
  past: TimelineSnapshot[],
  present: TimelineSnapshot,
  next: TimelineSnapshot,
  limit = 20,
): { past: TimelineSnapshot[]; present: TimelineSnapshot; future: TimelineSnapshot[] } {
  if (snapshotsEqual(present, next)) return { past, present, future: [] };
  return {
    past: [...past, present].slice(-Math.max(1, limit)),
    present: next,
    future: [],
  };
}
