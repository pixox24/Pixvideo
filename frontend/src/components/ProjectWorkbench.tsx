import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, ExternalLink, List, Music, PanelRight, Pause, Play, RefreshCw, Save, Settings2, SkipBack, SkipForward, X } from "lucide-react";
import { GenerationRun, Project, WorkbenchResources } from "../types";
import { cancelGenerationRun, createExport, fetchActiveGenerationRun, fetchGenerationRun, fetchProject, patchProject, pauseGenerationRun, patchScene, regenerateImage, regenerateTts, retryExport, retryFailedGeneration, resumeGenerationRun, selectAssetVersion, startGenerationRun, submitBatchImageGeneration, updateTimeline, uploadSceneAsset } from "../lib/workbenchApi";
import { initialGenerationState, reduceRunActionFailed, reduceRunActionFinished, reduceRunFetched, reduceRunStarted, ProjectGenerationState, shouldRefreshProject } from "../lib/projectGenerationState";
import { buildTimelineLayout, clampTimelineTime, findSceneAtTime, formatTimelineTime, getSceneLocalTime, getTimelineDuration, pushTimelineHistory, snapshotFromScenes, TimelineLayoutItem, TimelineSnapshot } from "../lib/workbenchState";
import { SceneList } from "./SceneList";
import { SceneInspector } from "./SceneInspector";
import { GenerationQueue } from "./GenerationQueue";
import { WorkbenchTimeline } from "./WorkbenchTimeline";
import { ExportDialog } from "./ExportDialog";
import { GenerationRunPanel } from "./GenerationRunPanel";
import { SceneProgressGrid } from "./SceneProgressGrid";
import { dismissWorkbenchKeysTip, isWorkbenchKeysTipDismissed } from "../lib/onboarding";

const PLAYBACK_MAX_FRAME_DELTA = 0.25;
const SEEK_STEP_SECONDS = 0.1;
/** Only correct audio when timeline/audio diverge meaningfully — avoids choppy seeks. */
const AUDIO_DRIFT_THRESHOLD = 0.35;
/** Throttle React clock updates during play so the whole workbench is not re-rendered at 60fps. */
const UI_TICK_MS = 50;

const requestPlaybackFrame = (callback: (time: number) => void): number => (
  typeof window.requestAnimationFrame === "function"
    ? window.requestAnimationFrame(callback)
    : window.setTimeout(() => callback(Date.now()), 16)
);
const cancelPlaybackFrame = (id: number) => {
  if (typeof window.cancelAnimationFrame === "function") window.cancelAnimationFrame(id);
  else window.clearTimeout(id);
};

/** Chrome aborts play() when pause()/src change races the pending promise — not a real failure. */
const isPlayInterruptedError = (error: unknown): boolean => {
  if (!error || typeof error !== "object") return false;
  const name = "name" in error ? String((error as { name?: unknown }).name) : "";
  const message = "message" in error ? String((error as { message?: unknown }).message) : "";
  return name === "AbortError" || message.includes("interrupted by a call to pause");
};

const safePlay = (
  audio: HTMLAudioElement,
  onError?: (error: unknown) => void,
): void => {
  const result = audio.play();
  if (result && typeof result.then === "function") {
    result.catch((error) => {
      if (isPlayInterruptedError(error)) return;
      onError?.(error);
    });
  }
};

export const ProjectWorkbench: React.FC<{ projectId: string; resources?: WorkbenchResources; addToast: (text: unknown, type: "success" | "error" | "info") => void }> = ({ projectId, resources, addToast }) => {
  const [project, setProject] = useState<Project | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [selectedSceneIds, setSelectedSceneIds] = useState<Set<string>>(new Set());
  const [batchPrefix, setBatchPrefix] = useState("");
  const [batchBusy, setBatchBusy] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [projectSettingsOpen, setProjectSettingsOpen] = useState(false);
  const [queueExpanded, setQueueExpanded] = useState(false);
  const [showKeysTip, setShowKeysTip] = useState(() => !isWorkbenchKeysTipDismissed());
  const [mobilePanel, setMobilePanel] = useState<"scenes" | "inspector" | null>(null);
  const [generation, setGeneration] = useState<ProjectGenerationState>(initialGenerationState);
  const [settings, setSettings] = useState({ bgm: "bgm-none", bgmVolume: 30, enableSubtitles: true });
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [pixelsPerSecond, setPixelsPerSecond] = useState(24);
  const [timelinePast, setTimelinePast] = useState<TimelineSnapshot[]>([]);
  const [timelinePresent, setTimelinePresent] = useState<TimelineSnapshot>({ sceneIds: [], holds: {} });
  const [timelineFuture, setTimelineFuture] = useState<TimelineSnapshot[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const bgmAudioRef = useRef<HTMLAudioElement | null>(null);
  const currentTimeRef = useRef(0);
  const isPlayingRef = useRef(false);
  const layoutRef = useRef<TimelineLayoutItem[]>([]);
  const currentSceneItemRef = useRef<TimelineLayoutItem | null>(null);
  const totalDurationRef = useRef(0);
  const projectRef = useRef<Project | null>(null);
  const selectedBgmSrcRef = useRef<string | null>(null);
  const togglePlayRef = useRef<() => void>(() => {});
  const lastSeekRef = useRef<{ sceneId: string; localTime: number } | null>(null);
  const audioErrorSceneRef = useRef<string | null>(null);
  const bgmErrorRef = useRef<string | null>(null);
  const playPromiseBusyRef = useRef(false);
  const bgmPlayPromiseBusyRef = useRef(false);
  const latestRunRef = useRef<GenerationRun | null>(null);
  const timelineSaveChainRef = useRef<Promise<void>>(Promise.resolve());
  const timelinePresentRef = useRef(timelinePresent);
  const activeProjectIdRef = useRef(projectId);
  const addToastRef = useRef(addToast);
  useEffect(() => { addToastRef.current = addToast; }, [addToast]);

  const load = async () => { try { const next = await fetchProject(projectId); setProject(next); setSelectedSceneId((current) => current || next.scenes[0]?.sceneId || null); } catch (error) { addToast(error, "error"); } };
  useEffect(() => {
    activeProjectIdRef.current = projectId;
    timelineSaveChainRef.current = Promise.resolve();
    latestRunRef.current = null;
    setGeneration(initialGenerationState);
    setIsPlaying(false);
    currentTimeRef.current = 0;
    setCurrentTime(0);
    void (async () => {
      await load();
      try {
        const activeRun = await fetchActiveGenerationRun(projectId);
        if (activeRun) {
          latestRunRef.current = activeRun;
          setGeneration((current) => reduceRunStarted(current, activeRun));
        }
      } catch (error) { addToast(error, "error"); }
    })();
  }, [projectId]);
  useEffect(() => {
    const runId = generation.run?.runId;
    if (!runId || !generation.polling) return;
    let busy = false;
    const timer = window.setInterval(async () => {
      if (busy) return; busy = true;
      try {
        const next = await fetchGenerationRun(projectId, runId);
        const previous = latestRunRef.current;
        latestRunRef.current = next;
        setGeneration((current) => reduceRunFetched(current, next));
        if (shouldRefreshProject(previous, next)) await load();
      }
      catch (error) { setGeneration((current) => ({ ...current, error, polling: false })); }
      finally { busy = false; }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [projectId, generation.run?.runId, generation.polling]);

  const hasActiveJobs = useMemo(() => (
    project?.jobs.some((job) => job.status === "pending" || job.status === "running")
    || project?.latestExport?.status === "pending"
    || project?.latestExport?.status === "running"
    || false
  ), [project?.jobs, project?.latestExport?.status]);
  useEffect(() => {
    if (!hasActiveJobs) return;
    let busy = false;
    const timer = window.setInterval(async () => {
      if (busy) return;
      busy = true;
      try { await load(); }
      catch { /* polling errors are non-fatal */ }
      finally { busy = false; }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [hasActiveJobs, projectId]);
  useEffect(() => {
    if (!project) return;
    const config = project.config || {};
    const rawVolume = Number(config.bgmVolume ?? config.bgm_volume ?? 30);
    setSettings({
      bgm: String(config.bgm ?? config.bgm_path ?? "bgm-none"),
      bgmVolume: Math.round(rawVolume <= 1 ? rawVolume * 100 : rawVolume),
      enableSubtitles: config.enableSubtitles !== false && config.subtitle_enabled !== false,
    });
  }, [project?.projectId]);
  useEffect(() => {
    if (!project?.dirty) return;
    const handler = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [project?.dirty]);

  const layout = useMemo(() => buildTimelineLayout(project?.scenes ?? []), [project?.scenes]);
  const totalDuration = useMemo(() => getTimelineDuration(layout), [layout]);
  const currentSceneItem = useMemo(() => findSceneAtTime(layout, currentTime), [layout, currentTime]);
  useEffect(() => { layoutRef.current = layout; }, [layout]);
  useEffect(() => { currentSceneItemRef.current = currentSceneItem; }, [currentSceneItem]);
  useEffect(() => { totalDurationRef.current = totalDuration; }, [totalDuration]);
  useEffect(() => { currentTimeRef.current = currentTime; }, [currentTime]);
  useEffect(() => { isPlayingRef.current = isPlaying; }, [isPlaying]);
  useEffect(() => { projectRef.current = project; }, [project]);

  const selected = useMemo(() => project?.scenes.find((scene) => scene.sceneId === selectedSceneId) || null, [project, selectedSceneId]);
  const selectedBgm = useMemo(() => {
    if (!resources?.bgm || settings.bgm === "bgm-none") return null;
    return resources.bgm.find((item) => item.id === settings.bgm && item.src) || null;
  }, [resources?.bgm, settings.bgm]);
  useEffect(() => { selectedBgmSrcRef.current = selectedBgm?.src || null; }, [selectedBgm?.src]);
  const selectedIndex = selected && project ? project.scenes.findIndex((scene) => scene.sceneId === selected.sceneId) : -1;
  const act = async (action: () => Promise<unknown>, message: string) => { try { await action(); addToast(message, "success"); await load(); } catch (error) { addToast(error, "error"); throw error; } };
  useEffect(() => {
    if (!project) return;
    setTimelinePresent(snapshotFromScenes(project.scenes));
  }, [project?.scenes]);
  useEffect(() => { timelinePresentRef.current = timelinePresent; }, [timelinePresent]);
  useEffect(() => {
    setTimelinePast([]);
    setTimelineFuture([]);
    setTimelinePresent({ sceneIds: [], holds: {} });
  }, [projectId]);
  const applyTimeline = async (sceneIds: string[], holds: Record<string, number>, message: string) => {
    const operation = timelineSaveChainRef.current.then(async () => {
      if (activeProjectIdRef.current !== projectId) return;
      try {
        await updateTimeline(projectId, sceneIds, holds);
        if (activeProjectIdRef.current !== projectId) return;
        addToast(message, "success");
        await load();
      } catch (error) {
        if (activeProjectIdRef.current !== projectId) return;
        addToast(error, "error");
        await load();
      }
    });
    timelineSaveChainRef.current = operation.catch(() => {});
    return operation;
  };
  const handleTimelineReorder = (ids: string[]) => {
    if (!project) return;
    const present = timelinePresentRef.current.sceneIds.length > 0 ? timelinePresentRef.current : snapshotFromScenes(project.scenes);
    const next = { sceneIds: ids, holds: { ...present.holds } };
    const result = pushTimelineHistory(timelinePast, present, next);
    setTimelinePast(result.past);
    timelinePresentRef.current = result.present;
    setTimelinePresent(result.present);
    setTimelineFuture([]);
    void applyTimeline(result.present.sceneIds, result.present.holds, "时间线顺序已保存");
  };
  const handleTimelineHold = (sceneId: string, hold: number) => {
    if (!project) return;
    const present = timelinePresentRef.current.sceneIds.length > 0 ? timelinePresentRef.current : snapshotFromScenes(project.scenes);
    const value = Math.max(0, hold);
    const next = { sceneIds: [...present.sceneIds], holds: { ...present.holds, [sceneId]: value } };
    const result = pushTimelineHistory(timelinePast, present, next);
    setTimelinePast(result.past);
    timelinePresentRef.current = result.present;
    setTimelinePresent(result.present);
    setTimelineFuture([]);
    void applyTimeline(result.present.sceneIds, result.present.holds, "停留时长已保存");
  };
  const handleUndo = () => {
    if (timelinePast.length === 0 || !project) return;
    const previous = timelinePast[timelinePast.length - 1];
    const present = timelinePresentRef.current;
    setTimelinePast(timelinePast.slice(0, -1));
    setTimelineFuture((future) => [present, ...future]);
    timelinePresentRef.current = previous;
    setTimelinePresent(previous);
    void applyTimeline(previous.sceneIds, previous.holds, "已撤销时间线操作");
  };
  const handleRedo = () => {
    if (timelineFuture.length === 0 || !project) return;
    const next = timelineFuture[0];
    const present = timelinePresentRef.current;
    setTimelineFuture(timelineFuture.slice(1));
    setTimelinePast((past) => [...past, present]);
    timelinePresentRef.current = next;
    setTimelinePresent(next);
    void applyTimeline(next.sceneIds, next.holds, "已重做时间线操作");
  };
  const currentVersion = selected?.versions.find((version) => version.versionId === selected.currentVersionId);
  const toggleScene = (sceneId: string) => setSelectedSceneIds((current) => { const next = new Set(current); if (next.has(sceneId)) next.delete(sceneId); else next.add(sceneId); return next; });
  const runAction = async (action: string, request: () => Promise<GenerationRun>) => { setGeneration((current) => ({ ...current, actionBusy: action, error: null })); try { const next = await request(); setGeneration((current) => reduceRunActionFinished(current, next)); await load(); } catch (error) { setGeneration((current) => reduceRunActionFailed(current, error)); addToast(error, "error"); } };
  const startRun = () => runAction("start", async () => { const next = await startGenerationRun(projectId); setGeneration((current) => reduceRunStarted(current, next)); return next; });
  const submitBatch = async () => { setBatchBusy(true); try { await act(() => submitBatchImageGeneration(projectId, [...selectedSceneIds], batchPrefix), "批量图片任务已提交"); } finally { setBatchBusy(false); } };
  const submitExport = async (allowIncomplete: boolean) => {
    const result = await createExport(projectId, allowIncomplete);
    setProject((current) => current ? { ...current, jobs: [...current.jobs, { jobId: result.jobId, taskId: result.taskId, kind: "export", status: result.status, progress: 0 }] } : current);
    if (result.candidateWarnings?.length) addToast(`已提交导出，${result.candidateWarnings.length} 个场景仍使用当前版本`, "info");
    else addToast("导出任务已提交", "success");
    return result;
  };
  const retryInitialExport = async () => {
    if (!project.latestExport) return;
    try {
      const result = await retryExport(projectId, project.latestExport.exportId);
      addToast("初稿导出已重新提交", "success");
      setProject((current) => current ? { ...current, jobs: [...current.jobs, { jobId: result.jobId, taskId: result.taskId, kind: "export", status: result.status, progress: 0 }] } : current);
      await load();
    } catch (error) { addToast(error, "error"); }
  };
  const saveSettings = async () => {
    if (!project) return;
    setSettingsBusy(true);
    try {
      const next = await patchProject(projectId, {
        config: { bgm: settings.bgm, bgmVolume: settings.bgmVolume, enableSubtitles: settings.enableSubtitles },
        expectedUpdatedAt: project.updatedAt,
      });
      setProject(next);
      addToast("项目设置已保存", "success");
    } catch (error) { addToast(error, "error"); }
    finally { setSettingsBusy(false); }
  };

  /**
   * Drive narration audio from the ref clock — never from a currentTime useEffect.
   * Binding play/pause to every React tick races HTMLMediaElement.play() against pause()
   * (Chrome: "The play() request was interrupted by a call to pause()").
   */
  const syncNarrationAudio = useCallback((opts?: { forceSeek?: boolean }) => {
    const audio = audioRef.current;
    const proj = projectRef.current;
    if (!audio || !proj) return;

    const item = findSceneAtTime(layoutRef.current, currentTimeRef.current);
    currentSceneItemRef.current = item;
    const scene = item ? proj.scenes.find((candidate) => candidate.sceneId === item.sceneId) : null;
    if (!item || !scene) {
      if (!audio.paused) audio.pause();
      return;
    }

    const localTime = getSceneLocalTime(item, currentTimeRef.current);
    const inAudioRegion = localTime < item.audioDurationSeconds && Boolean(scene.audioUrl);
    const playing = isPlayingRef.current;

    if (audio.dataset.scene !== item.sceneId) {
      if (!audio.paused) audio.pause();
      playPromiseBusyRef.current = false;
      audio.dataset.scene = item.sceneId;
      if (inAudioRegion && scene.audioUrl) {
        lastSeekRef.current = { sceneId: item.sceneId, localTime };
        audio.dataset.loaded = "0";
        audio.src = scene.audioUrl;
        // currentTime is applied in onLoadedMetadata once the new source is ready.
      } else {
        lastSeekRef.current = null;
        audio.dataset.loaded = "0";
        audio.removeAttribute("src");
        audio.load();
      }
      return;
    }

    if (audio.dataset.loaded !== "1") {
      // Wait for onLoadedMetadata; do not re-assign src every frame (restarts download).
      if (inAudioRegion && scene.audioUrl && !audio.getAttribute("src")) {
        lastSeekRef.current = { sceneId: item.sceneId, localTime };
        audio.src = scene.audioUrl;
      }
      if (!playing || !inAudioRegion) {
        if (!audio.paused) audio.pause();
        playPromiseBusyRef.current = false;
      }
      return;
    }

    // Apply seek even while paused so resume continues from the scrub position.
    if (inAudioRegion && (opts?.forceSeek || Math.abs((audio.currentTime || 0) - localTime) > AUDIO_DRIFT_THRESHOLD)) {
      lastSeekRef.current = { sceneId: item.sceneId, localTime };
      try {
        audio.currentTime = localTime;
      } catch {
        /* seek before ready — metadata handler will apply lastSeekRef */
      }
    }

    if (!playing || !inAudioRegion) {
      if (!audio.paused) audio.pause();
      playPromiseBusyRef.current = false;
      return;
    }

    if (audio.paused && !playPromiseBusyRef.current) {
      playPromiseBusyRef.current = true;
      const result = audio.play();
      if (result && typeof result.then === "function") {
        result
          .then(() => { playPromiseBusyRef.current = false; })
          .catch((error) => {
            playPromiseBusyRef.current = false;
            if (isPlayInterruptedError(error)) return;
            addToastRef.current(error, "error");
          });
      } else {
        playPromiseBusyRef.current = false;
      }
    }
  }, []);

  const syncBgmAudio = useCallback((opts?: { forceSeek?: boolean }) => {
    const audio = bgmAudioRef.current;
    const src = selectedBgmSrcRef.current;
    if (!audio || !src || totalDurationRef.current <= 0) {
      if (audio && !audio.paused) audio.pause();
      return;
    }
    if (Number.isFinite(audio.duration) && audio.duration > 0) {
      const target = currentTimeRef.current % audio.duration;
      if (opts?.forceSeek || Math.abs(audio.currentTime - target) > AUDIO_DRIFT_THRESHOLD) {
        try {
          audio.currentTime = target;
        } catch {
          /* ignore unready seeks */
        }
      }
    }
    if (!isPlayingRef.current) {
      if (!audio.paused) audio.pause();
      bgmPlayPromiseBusyRef.current = false;
      return;
    }
    if (audio.paused && !bgmPlayPromiseBusyRef.current) {
      bgmPlayPromiseBusyRef.current = true;
      const result = audio.play();
      if (result && typeof result.then === "function") {
        result
          .then(() => { bgmPlayPromiseBusyRef.current = false; })
          .catch((error) => {
            bgmPlayPromiseBusyRef.current = false;
            if (isPlayInterruptedError(error)) return;
            if (bgmErrorRef.current !== src) {
              bgmErrorRef.current = src;
              addToastRef.current(error, "error");
            }
          });
      } else {
        bgmPlayPromiseBusyRef.current = false;
      }
    }
  }, []);

  const seek = useCallback((time: number) => {
    const next = clampTimelineTime(time, totalDurationRef.current || totalDuration);
    currentTimeRef.current = next;
    setCurrentTime(next);
    // Keep audio/timeline aligned after scrubbing without waiting for the next rAF.
    syncNarrationAudio({ forceSeek: true });
    syncBgmAudio({ forceSeek: true });
  }, [totalDuration, syncNarrationAudio, syncBgmAudio]);
  const goToAdjacentScene = useCallback((offset: number) => {
    const activeLayout = layoutRef.current.length > 0 ? layoutRef.current : layout;
    const item = currentSceneItemRef.current ?? currentSceneItem;
    if (!item || activeLayout.length === 0) return;
    const index = activeLayout.findIndex((candidate) => candidate.sceneId === item.sceneId);
    const target = activeLayout[Math.min(Math.max(index + offset, 0), activeLayout.length - 1)];
    if (target) seek(target.startSeconds);
  }, [currentSceneItem, layout, seek]);
  const togglePlay = useCallback(() => {
    if (!project || project.scenes.length === 0) return;
    if (isPlayingRef.current) { setIsPlaying(false); return; }
    const duration = totalDurationRef.current || totalDuration;
    if (currentTimeRef.current >= duration - 0.001) {
      currentTimeRef.current = 0;
      setCurrentTime(0);
    }
    setIsPlaying(true);
  }, [project, totalDuration]);
  useEffect(() => { togglePlayRef.current = togglePlay; }, [togglePlay]);

  useEffect(() => {
    if (!isPlaying) {
      // Leaving play mode: stop media without racing a pending play() via effect churn.
      audioRef.current?.pause();
      bgmAudioRef.current?.pause();
      playPromiseBusyRef.current = false;
      bgmPlayPromiseBusyRef.current = false;
      return;
    }
    let rafId = 0;
    let lastFrameAt = 0;
    let lastUiAt = 0;
    // Kick media once when entering play (metadata handlers may finish the start).
    syncNarrationAudio({ forceSeek: true });
    syncBgmAudio({ forceSeek: true });
    const tick = (now: number) => {
      const delta = lastFrameAt === 0 ? 0 : Math.min((now - lastFrameAt) / 1000, PLAYBACK_MAX_FRAME_DELTA);
      lastFrameAt = now;
      const duration = totalDurationRef.current || totalDuration;
      const next = clampTimelineTime(currentTimeRef.current + delta, duration);
      currentTimeRef.current = next;
      // Audio follows the high-frequency ref clock; React UI is throttled to reduce jank.
      syncNarrationAudio();
      syncBgmAudio();
      if (lastUiAt === 0 || now - lastUiAt >= UI_TICK_MS || next >= duration) {
        lastUiAt = now;
        setCurrentTime(next);
      }
      if (next >= duration) {
        setIsPlaying(false);
        return;
      }
      rafId = requestPlaybackFrame(tick);
    };
    rafId = requestPlaybackFrame(tick);
    return () => cancelPlaybackFrame(rafId);
  }, [isPlaying, totalDuration, syncNarrationAudio, syncBgmAudio]);

  useEffect(() => {
    if (currentSceneItem) setSelectedSceneId(currentSceneItem.sceneId);
  }, [currentSceneItem?.sceneId]);

  useEffect(() => {
    const audio = bgmAudioRef.current;
    if (!audio) return;
    audio.pause();
    bgmPlayPromiseBusyRef.current = false;
    audio.currentTime = 0;
    audio.removeAttribute("src");
    audio.load();
    bgmErrorRef.current = null;
    if (selectedBgm?.src) {
      audio.src = selectedBgm.src;
      audio.volume = Math.min(1, Math.max(0, settings.bgmVolume / 100));
      audio.load();
    }
    return () => {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    };
  }, [selectedBgm?.src]);

  useEffect(() => {
    const audio = bgmAudioRef.current;
    if (!audio) return;
    audio.volume = Math.min(1, Math.max(0, settings.bgmVolume / 100));
  }, [settings.bgmVolume]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName ?? "";
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target?.isContentEditable) return;
      if (event.code === "Space" || event.key === " ") {
        event.preventDefault();
        togglePlayRef.current?.();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        seek(currentTimeRef.current - SEEK_STEP_SECONDS);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        seek(currentTimeRef.current + SEEK_STEP_SECONDS);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [seek]);

  useEffect(() => {
    const onVisibilityChange = () => { if (document.hidden) setIsPlaying(false); };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, []);
  useEffect(() => () => {
    audioRef.current?.pause();
    bgmAudioRef.current?.pause();
  }, []);

  if (!project) {
    return (
      <div className="flex h-full min-h-[320px] items-center justify-center rounded-[var(--radius-lg)] border border-dashed border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] p-6 text-sm text-zinc-400">
        <div className="space-y-2 text-center">
          <LoaderLike />
          <p>正在加载项目…</p>
        </div>
      </div>
    );
  }

  const runIsTerminal = generation.run && ["completed", "completed_with_failures", "cancelled", "failed"].includes(generation.run.status);
  const pendingCount = generation.run && !runIsTerminal
    ? generation.run.items.filter((item) => !["completed", "skipped", "failed", "cancelled", "candidate_review"].includes(item.status)).length
    : project.scenes.filter((scene) => scene.generationState?.image !== "ready" || scene.generationState?.audio !== "ready").length;
  const exportJob = project.jobs.find((job) => job.kind === "export" && (job.status === "pending" || job.status === "running"));
  const latestExportActive = project.latestExport?.status === "pending" || project.latestExport?.status === "running";
  const candidateCount = project.scenes.reduce((count, scene) => count + (scene.generationState?.candidateCount || 0), 0);
  const staleOrMissingIds = project.scenes
    .filter((scene) => {
      const image = scene.generationState?.image;
      const audio = scene.generationState?.audio;
      return image === "stale" || audio === "stale" || image === "missing" || audio === "missing" || !scene.currentVersionId || !scene.audioUrl;
    })
    .map((scene) => scene.sceneId);
  const statusLabel = generation.run && !["completed", "completed_with_failures", "cancelled", "failed"].includes(generation.run.status)
    ? "正在生成素材"
    : exportJob || latestExportActive
      ? latestExportActive && project.latestExport?.purpose === "initial" ? "正在导出初稿" : "正在导出成片"
      : generation.run?.status === "completed_with_failures"
        ? "生成有失败项"
        : project.latestExport?.purpose === "initial" && project.latestExport.status === "completed"
          ? "初稿已完成"
          : !project.latestExport || project.latestExport.status === "failed"
            ? "尚未导出"
          : project.dirty
            ? "有未导出修改"
            : candidateCount > 0
              ? "有候选待确认"
              : null;
  const exportCompleted = project.latestExport?.status === "completed" && project.latestExport.outputUrl;
  const exportIsInitial = project.latestExport?.purpose === "initial";
  const regenerateStale = async () => {
    if (staleOrMissingIds.length === 0) {
      addToast("没有需要补生成的镜头", "info");
      return;
    }
    setGeneration((current) => ({ ...current, actionBusy: "start", error: null }));
    try {
      const next = await startGenerationRun(projectId, staleOrMissingIds);
      setGeneration((current) => reduceRunActionFinished(reduceRunStarted(current, next), next));
      await load();
      addToast(`已开始补生成 ${staleOrMissingIds.length} 个镜头`, "success");
    } catch (error) {
      setGeneration((current) => reduceRunActionFailed(current, error));
      addToast(error, "error");
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]">
      <GenerationRunPanel
        run={generation.run}
        busy={generation.actionBusy}
        pendingCount={pendingCount}
        exportStatus={project.latestExport?.status || null}
        exportPurpose={project.latestExport?.purpose || null}
        onStart={startRun}
        onPause={() => generation.run && void runAction("pause", () => pauseGenerationRun(projectId, generation.run!.runId))}
        onResume={() => generation.run && void runAction("resume", () => resumeGenerationRun(projectId, generation.run!.runId))}
        onCancel={() => generation.run && void runAction("cancel", () => cancelGenerationRun(projectId, generation.run!.runId))}
        onRetry={() => generation.run && void runAction("retry", () => retryFailedGeneration(projectId, generation.run!.runId))}
        onLocateFailure={(sceneId) => { setSelectedSceneId(sceneId); setMobilePanel(null); }}
      />

      {/* TOPBAR — single row */}
      <div className="flex h-14 shrink-0 flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] px-3">
        <div className="min-w-0">
          <div className="truncate font-display text-sm font-semibold text-zinc-100">{project.title}</div>
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            <span className="text-caption">{project.scenes.length} 个分镜</span>
            {statusLabel && <span className="ui-chip ui-chip-brand !py-0">{statusLabel}</span>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {staleOrMissingIds.length > 0 && (
            <button
              type="button"
              onClick={() => void regenerateStale()}
              disabled={generation.actionBusy !== null}
              className="ui-btn ui-btn-secondary ui-btn-sm"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              补生成 ({staleOrMissingIds.length})
            </button>
          )}
          {project.latestExport?.status === "failed" && (
            <button type="button" onClick={() => void retryInitialExport()} className="ui-btn ui-btn-outline ui-btn-sm text-rose-300">
              <RefreshCw className="h-3.5 w-3.5" />重试导出
            </button>
          )}
          {exportCompleted && (
            <a
              href={project.latestExport!.outputUrl!}
              target="_blank"
              rel="noreferrer"
              className="ui-btn ui-btn-secondary ui-btn-sm"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              {exportIsInitial ? "打开初稿" : "打开成片"}
            </a>
          )}
          <button
            type="button"
            aria-label="打开分镜面板"
            onClick={() => setMobilePanel(mobilePanel === "scenes" ? null : "scenes")}
            className="ui-btn ui-btn-ghost ui-btn-icon lg:hidden"
          >
            <List className="h-4 w-4" />
          </button>
          <button
            type="button"
            aria-label="打开检查器"
            onClick={() => setMobilePanel(mobilePanel === "inspector" ? null : "inspector")}
            className="ui-btn ui-btn-ghost ui-btn-icon lg:hidden"
          >
            <PanelRight className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setProjectSettingsOpen(true)}
            className="ui-btn ui-btn-secondary ui-btn-sm"
          >
            <Settings2 className="h-3.5 w-3.5" />
            项目设置
          </button>
          <button type="button" onClick={() => setExportOpen(true)} className="ui-btn ui-btn-primary ui-btn-sm">
            <Download className="h-3.5 w-3.5" />导出成片
          </button>
          <button
            type="button"
            title="刷新项目"
            aria-label="刷新项目"
            onClick={() => void load()}
            className="ui-btn ui-btn-ghost ui-btn-icon"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {exportCompleted && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-emerald-500/15 bg-emerald-500/5 px-3 py-2">
          <p className="text-xs text-emerald-200">
            {exportIsInitial ? "初稿已导出完成" : "成片导出完成"}
            {latestExportActive ? " · 有新的导出任务进行中" : ""}
          </p>
          <div className="flex gap-2">
            <a
              href={project.latestExport!.outputUrl!}
              target="_blank"
              rel="noreferrer"
              className="ui-btn ui-btn-secondary ui-btn-sm"
            >
              打开{exportIsInitial ? "初稿" : "成片"}
            </a>
            <a
              href={project.latestExport!.outputUrl!}
              download
              className="ui-btn ui-btn-secondary ui-btn-sm text-emerald-200"
            >
              下载
            </a>
          </div>
        </div>
      )}

      <SceneProgressGrid
        scenes={project.scenes}
        run={generation.run}
        selectedSceneId={selectedSceneId}
        onSelect={(id) => { setSelectedSceneId(id); setMobilePanel(null); }}
      />

      {showKeysTip && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-500/15 bg-amber-500/5 px-3 py-1.5 animate-fade-in">
          <p className="text-caption text-amber-100/80">
            快捷键：
            <span className="kbd mx-1">Space</span> 播放/暂停
            <span className="kbd mx-1">←</span>
            <span className="kbd mx-1">→</span> 微调时间
          </p>
          <button
            type="button"
            onClick={() => {
              dismissWorkbenchKeysTip();
              setShowKeysTip(false);
            }}
            className="text-caption text-amber-200/70 hover:text-amber-100"
          >
            知道了
          </button>
        </div>
      )}

      {selectedSceneIds.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] px-3 py-2">
          <span className="text-xs text-zinc-300">选中 {selectedSceneIds.size} 项</span>
          <input
            value={batchPrefix}
            onChange={(event) => setBatchPrefix(event.target.value)}
            placeholder="提示词前缀"
            className="ui-input min-w-40 flex-1"
          />
          <button type="button" disabled={batchBusy} onClick={() => void submitBatch()} className="ui-btn ui-btn-primary ui-btn-sm">
            批量重新生成
          </button>
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(200px,240px)_minmax(0,1fr)_minmax(260px,320px)]">
        <SceneList
          className={mobilePanel === "scenes" ? "flex" : "hidden lg:flex"}
          scenes={project.scenes}
          selectedSceneId={selectedSceneId}
          selectedSceneIds={selectedSceneIds}
          onSelect={(id) => { setSelectedSceneId(id); setMobilePanel(null); }}
          onToggle={toggleScene}
        />
        <main
          className={`${mobilePanel ? "hidden lg:flex" : "flex"} min-h-0 min-w-0 flex-col bg-[var(--color-surface-0)] p-3 sm:p-4`}
        >
          <div className="mb-3 flex items-center justify-between">
            <div className="text-xs text-zinc-400">
              {selected ? `分镜 #${selectedIndex + 1} · ${selected.durationSeconds.toFixed(1)} 秒` : "未选择分镜"}
              <span className="ml-3 font-mono text-zinc-500">
                {formatTimelineTime(currentTime)} / {formatTimelineTime(totalDuration)}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                title="上一个分镜"
                aria-label="上一个分镜"
                onClick={() => goToAdjacentScene(-1)}
                className="ui-btn ui-btn-ghost ui-btn-icon disabled:opacity-30"
                disabled={!currentSceneItem && !currentSceneItemRef.current}
              >
                <SkipBack className="h-4 w-4" />
              </button>
              <button
                type="button"
                title={isPlaying ? "暂停播放" : "播放项目"}
                aria-label={isPlaying ? "暂停播放" : "播放项目"}
                onClick={() => togglePlay()}
                disabled={project.scenes.length === 0}
                className="flex h-11 w-11 items-center justify-center rounded-full bg-amber-500 text-black shadow-[var(--shadow-cta)] transition-colors hover:bg-amber-400 disabled:opacity-30"
              >
                {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 pl-0.5" />}
              </button>
              <button
                type="button"
                title="下一个分镜"
                aria-label="下一个分镜"
                onClick={() => goToAdjacentScene(1)}
                className="ui-btn ui-btn-ghost ui-btn-icon disabled:opacity-30"
                disabled={!currentSceneItem && !currentSceneItemRef.current}
              >
                <SkipForward className="h-4 w-4" />
              </button>
            </div>
          </div>
          <div className="ui-stage min-h-0 flex-1 text-xs text-zinc-600">
            {currentVersion ? (
              <img src={currentVersion.imageUrl} alt="画面预览" className="max-h-full max-w-full object-contain" />
            ) : (
              <>画面预览{selected ? ` · #${selectedIndex + 1}` : ""}</>
            )}
          </div>
          <audio
            ref={audioRef}
            className="hidden"
            preload="auto"
            onLoadedMetadata={() => {
              const audio = audioRef.current;
              if (!audio) return;
              audio.dataset.loaded = "1";
              const pending = lastSeekRef.current;
              if (pending && audio.dataset.scene === pending.sceneId) {
                try {
                  audio.currentTime = pending.localTime;
                } catch {
                  /* ignore */
                }
              }
              if (isPlayingRef.current && audio.paused) {
                safePlay(audio);
              }
            }}
            onError={() => {
              const audio = audioRef.current;
              if (!audio) return;
              audio.dataset.loaded = "0";
              playPromiseBusyRef.current = false;
              const sceneId = audio.dataset.scene;
              if (audioErrorSceneRef.current !== sceneId) {
                audioErrorSceneRef.current = sceneId;
                addToast("旁白音频加载失败", "error");
              }
            }}
          />
          <audio
            ref={bgmAudioRef}
            className="hidden"
            preload="auto"
            loop
            onLoadedMetadata={() => {
              const audio = bgmAudioRef.current;
              if (!audio || !selectedBgmSrcRef.current || !Number.isFinite(audio.duration) || audio.duration <= 0) return;
              try {
                audio.currentTime = currentTimeRef.current % audio.duration;
              } catch {
                /* ignore */
              }
              if (isPlayingRef.current && audio.paused) {
                safePlay(audio);
              }
            }}
            onError={() => {
              bgmPlayPromiseBusyRef.current = false;
              const src = selectedBgmSrcRef.current;
              if (src && bgmErrorRef.current !== src) {
                bgmErrorRef.current = src;
                addToast("背景音乐加载失败，已继续播放旁白", "error");
              }
            }}
          />
        </main>
        <SceneInspector
          className={`${mobilePanel === "inspector" ? "block" : "hidden lg:block"} min-h-0`}
          scene={selected}
          onSave={(patch) => selected ? act(() => patchScene(projectId, selected.sceneId, patch), "场景草稿已保存") : Promise.resolve()}
          onRegenerateImage={(prompt) => selected ? act(() => regenerateImage(projectId, selected.sceneId, prompt), "图片生成任务已提交") : Promise.resolve()}
          onRegenerateTts={(narration) => selected ? act(() => regenerateTts(projectId, selected.sceneId, narration), "配音生成任务已提交") : Promise.resolve()}
          onUpload={(file) => selected ? act(() => uploadSceneAsset(projectId, selected.sceneId, file), "素材已上传为候选版本") : Promise.resolve()}
          onSelectVersion={(versionId) => selected ? act(() => selectAssetVersion(projectId, selected.sceneId, versionId), "已切换当前版本") : Promise.resolve()}
        />
      </div>

      <div className="shrink-0 border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-2">
        <div className="ui-panel !p-2">
          <WorkbenchTimeline
            scenes={project.scenes}
            selectedSceneId={selectedSceneId}
            currentTime={currentTime}
            totalDuration={totalDuration}
            isPlaying={isPlaying}
            pixelsPerSecond={pixelsPerSecond}
            canUndo={timelinePast.length > 0}
            canRedo={timelineFuture.length > 0}
            onZoomChange={(value) => setPixelsPerSecond(Math.min(120, Math.max(8, value)))}
            onSeek={seek}
            onPause={() => setIsPlaying(false)}
            onSelect={setSelectedSceneId}
            onReorder={handleTimelineReorder}
            onHold={handleTimelineHold}
            onUndo={handleUndo}
            onRedo={handleRedo}
          />
        </div>
      </div>

      <GenerationQueue jobs={project.jobs} expanded={queueExpanded} onToggle={() => setQueueExpanded((v) => !v)} />
      <ExportDialog
        project={project}
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        onExport={submitExport}
        onLocateScene={(sceneId) => { setSelectedSceneId(sceneId); setExportOpen(false); }}
      />

      {/* Project settings drawer — BGM / subtitles (logic unchanged) */}
      {projectSettingsOpen && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
            aria-label="关闭项目设置"
            onClick={() => setProjectSettingsOpen(false)}
          />
          <aside
            className="fixed inset-y-0 right-0 z-50 flex w-[min(400px,100vw)] flex-col border-l border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] shadow-[var(--shadow-soft)] animate-fade-in"
            role="dialog"
            aria-label="项目设置"
          >
            <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-zinc-100">
                <Music className="h-4 w-4 text-amber-500" />
                项目设置
              </div>
              <button
                type="button"
                className="ui-btn ui-btn-ghost ui-btn-icon"
                aria-label="关闭"
                onClick={() => setProjectSettingsOpen(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="space-y-4 overflow-y-auto p-4">
              <label className="block space-y-1.5">
                <span className="text-label">背景音乐</span>
                <select
                  value={settings.bgm}
                  onChange={(event) => setSettings((current) => ({ ...current, bgm: event.target.value }))}
                  className="ui-input"
                >
                  <option value="bgm-none">无背景音乐</option>
                  {(resources?.bgm || [])
                    .filter((item) => item.id !== "bgm-none")
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                </select>
              </label>
              <label className="block space-y-1.5">
                <span className="text-label">音量 · {settings.bgmVolume}%</span>
                <input
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={settings.bgmVolume}
                  onChange={(event) =>
                    setSettings((current) => ({ ...current, bgmVolume: Number(event.target.value) }))
                  }
                  className="w-full accent-amber-500"
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-zinc-300">
                <input
                  type="checkbox"
                  checked={settings.enableSubtitles}
                  onChange={(event) =>
                    setSettings((current) => ({ ...current, enableSubtitles: event.target.checked }))
                  }
                  className="accent-amber-500"
                />
                启用字幕
              </label>
            </div>
            <div className="mt-auto border-t border-[var(--color-border-subtle)] p-4">
              <button
                type="button"
                disabled={settingsBusy}
                onClick={() => void saveSettings()}
                className="ui-btn ui-btn-primary w-full"
              >
                <Save className="h-3.5 w-3.5" />
                {settingsBusy ? "保存中" : "保存设置"}
              </button>
            </div>
          </aside>
        </>
      )}
    </div>
  );
};

function LoaderLike() {
  return <div className="mx-auto h-5 w-5 animate-spin rounded-full border-2 border-zinc-700 border-t-amber-500" />;
}
