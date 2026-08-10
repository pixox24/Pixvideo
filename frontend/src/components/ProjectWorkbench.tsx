import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download, List, Music, PanelRight, Pause, Play, RefreshCw, Save, SkipBack, SkipForward } from "lucide-react";
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

const PLAYBACK_MAX_FRAME_DELTA = 0.25;
const SEEK_STEP_SECONDS = 0.1;
const AUDIO_DRIFT_THRESHOLD = 0.3;

const requestPlaybackFrame = (callback: (time: number) => void): number => (
  typeof window.requestAnimationFrame === "function"
    ? window.requestAnimationFrame(callback)
    : window.setTimeout(() => callback(Date.now()), 16)
);
const cancelPlaybackFrame = (id: number) => {
  if (typeof window.cancelAnimationFrame === "function") window.cancelAnimationFrame(id);
  else window.clearTimeout(id);
};

export const ProjectWorkbench: React.FC<{ projectId: string; resources?: WorkbenchResources; addToast: (text: unknown, type: "success" | "error" | "info") => void }> = ({ projectId, resources, addToast }) => {
  const [project, setProject] = useState<Project | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [selectedSceneIds, setSelectedSceneIds] = useState<Set<string>>(new Set());
  const [batchPrefix, setBatchPrefix] = useState("");
  const [batchBusy, setBatchBusy] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
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
  const togglePlayRef = useRef<() => void>(() => {});
  const lastSeekRef = useRef<{ sceneId: string; localTime: number } | null>(null);
  const audioErrorSceneRef = useRef<string | null>(null);
  const bgmErrorRef = useRef<string | null>(null);
  const latestRunRef = useRef<GenerationRun | null>(null);
  const timelineSaveChainRef = useRef<Promise<void>>(Promise.resolve());
  const timelinePresentRef = useRef(timelinePresent);
  const activeProjectIdRef = useRef(projectId);

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

  const selected = useMemo(() => project?.scenes.find((scene) => scene.sceneId === selectedSceneId) || null, [project, selectedSceneId]);
  const selectedBgm = useMemo(() => {
    if (!resources?.bgm || settings.bgm === "bgm-none") return null;
    return resources.bgm.find((item) => item.id === settings.bgm && item.src) || null;
  }, [resources?.bgm, settings.bgm]);
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

  const seek = useCallback((time: number) => {
    const next = clampTimelineTime(time, totalDurationRef.current || totalDuration);
    currentTimeRef.current = next;
    setCurrentTime(next);
  }, [totalDuration]);
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
    if (!isPlaying) return;
    let rafId = 0;
    let lastFrameAt = 0;
    const tick = (now: number) => {
      const delta = lastFrameAt === 0 ? 0 : Math.min((now - lastFrameAt) / 1000, PLAYBACK_MAX_FRAME_DELTA);
      lastFrameAt = now;
      const duration = totalDurationRef.current || totalDuration;
      const next = clampTimelineTime(currentTimeRef.current + delta, duration);
      currentTimeRef.current = next;
      setCurrentTime(next);
      if (next >= duration) {
        setIsPlaying(false);
        return;
      }
      rafId = requestPlaybackFrame(tick);
    };
    rafId = requestPlaybackFrame(tick);
    return () => cancelPlaybackFrame(rafId);
  }, [isPlaying, totalDuration]);

  useEffect(() => {
    if (currentSceneItem) setSelectedSceneId(currentSceneItem.sceneId);
  }, [currentSceneItem?.sceneId]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio || !project) return;
    const item = currentSceneItem;
    const scene = item ? project.scenes.find((candidate) => candidate.sceneId === item.sceneId) : null;
    if (!item || !scene) { audio.pause(); return; }
    const localTime = getSceneLocalTime(item, currentTime);
    const inAudioRegion = localTime < item.audioDurationSeconds && Boolean(scene.audioUrl);
    if (audio.dataset.scene !== item.sceneId) {
      audio.pause();
      audio.dataset.scene = item.sceneId;
      if (inAudioRegion) {
        audio.dataset.loaded = "1";
        lastSeekRef.current = { sceneId: item.sceneId, localTime };
        audio.src = scene.audioUrl!;
        audio.currentTime = localTime;
      } else {
        audio.dataset.loaded = "0";
        lastSeekRef.current = null;
        audio.removeAttribute("src");
        audio.load();
      }
    }
    if (!isPlaying || !inAudioRegion) {
      audio.pause();
      return;
    }
    if (audio.dataset.loaded !== "1") {
      lastSeekRef.current = { sceneId: item.sceneId, localTime };
      audio.src = scene.audioUrl!;
      audio.dataset.loaded = "1";
    }
    if (Math.abs((audio.currentTime || 0) - localTime) > AUDIO_DRIFT_THRESHOLD) {
      lastSeekRef.current = { sceneId: item.sceneId, localTime };
      audio.currentTime = localTime;
    }
    if (audio.paused) {
      audio.play().catch((error) => addToast(error, "error"));
    }
  }, [currentTime, isPlaying, layout, project, currentSceneItem]);

  useEffect(() => {
    const audio = bgmAudioRef.current;
    if (!audio) return;
    audio.pause();
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
    const audio = bgmAudioRef.current;
    if (!audio || !selectedBgm?.src || totalDuration <= 0) {
      audio?.pause();
      return;
    }
    if (!isPlaying) {
      audio.pause();
      return;
    }
    if (Number.isFinite(audio.duration) && audio.duration > 0) {
      const target = currentTime % audio.duration;
      if (Math.abs(audio.currentTime - target) > AUDIO_DRIFT_THRESHOLD) audio.currentTime = target;
    }
    if (audio.paused) audio.play().catch((error) => {
      if (bgmErrorRef.current !== selectedBgm.src) {
        bgmErrorRef.current = selectedBgm.src;
        addToast(error, "error");
      }
    });
  }, [currentTime, isPlaying, selectedBgm?.src, totalDuration, addToast]);

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

  if (!project) return <div className="p-6 text-sm text-zinc-400">正在加载项目…</div>;

  const runIsTerminal = generation.run && ["completed", "completed_with_failures", "cancelled", "failed"].includes(generation.run.status);
  const pendingCount = generation.run && !runIsTerminal
    ? generation.run.items.filter((item) => !["completed", "skipped", "failed", "cancelled", "candidate_review"].includes(item.status)).length
    : project.scenes.filter((scene) => scene.generationState?.image !== "ready" || scene.generationState?.audio !== "ready").length;
  const exportJob = project.jobs.find((job) => job.kind === "export" && (job.status === "pending" || job.status === "running"));
  const latestExportActive = project.latestExport?.status === "pending" || project.latestExport?.status === "running";
  const candidateCount = project.scenes.reduce((count, scene) => count + (scene.generationState?.candidateCount || 0), 0);
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
  return (
    <div className="flex min-h-[640px] flex-col overflow-hidden border border-zinc-800 bg-[#101114]">
      <GenerationRunPanel run={generation.run} busy={generation.actionBusy} pendingCount={pendingCount} onStart={startRun} onPause={() => generation.run && void runAction("pause", () => pauseGenerationRun(projectId, generation.run!.runId))} onResume={() => generation.run && void runAction("resume", () => resumeGenerationRun(projectId, generation.run!.runId))} onCancel={() => generation.run && void runAction("cancel", () => cancelGenerationRun(projectId, generation.run!.runId))} onRetry={() => generation.run && void runAction("retry", () => retryFailedGeneration(projectId, generation.run!.runId))} />
      <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-zinc-100">{project.title}</div>
          <div className="text-[10px] text-zinc-500">AI 剪辑工作台 · {project.scenes.length} 个分镜{statusLabel ? ` · ${statusLabel}` : ""}</div>
        </div>
        <div className="flex items-center gap-1">
          {project.latestExport?.status === "failed" && <button type="button" onClick={() => void retryInitialExport()} className="flex items-center gap-1 border border-red-900 px-3 py-2 text-xs text-red-300"><RefreshCw className="h-3.5 w-3.5" />重试初稿</button>}
          {project.latestExport?.outputUrl && <a href={project.latestExport.outputUrl} target="_blank" rel="noreferrer" className="flex items-center gap-1 border border-zinc-700 px-3 py-2 text-xs text-zinc-200"><Play className="h-3.5 w-3.5" />查看初稿</a>}
          <button type="button" aria-label="打开分镜面板" onClick={() => setMobilePanel(mobilePanel === "scenes" ? null : "scenes")} className="p-2 text-zinc-400 lg:hidden"><List className="h-4 w-4" /></button>
          <button type="button" aria-label="打开检查器" onClick={() => setMobilePanel(mobilePanel === "inspector" ? null : "inspector")} className="p-2 text-zinc-400 lg:hidden"><PanelRight className="h-4 w-4" /></button>
          <button type="button" onClick={() => setExportOpen(true)} className="flex items-center gap-1 bg-amber-500 px-3 py-2 text-xs font-semibold text-black"><Download className="h-3.5 w-3.5" />导出</button>
          <button type="button" title="刷新项目" aria-label="刷新项目" onClick={() => void load()} className="p-2 text-zinc-400 hover:text-zinc-100"><RefreshCw className="h-4 w-4" /></button>
        </div>
      </div>
      <section className="border-b border-zinc-800 bg-[#0d0e11] px-3 py-2">
        <div className="flex flex-wrap items-center gap-3">
          <Music className="h-4 w-4 text-zinc-500" />
          <label className="flex items-center gap-2 text-xs text-zinc-400">BGM
            <select value={settings.bgm} onChange={(event) => setSettings((current) => ({ ...current, bgm: event.target.value }))} className="border border-zinc-800 bg-black px-2 py-1 text-xs text-zinc-200">
              <option value="bgm-none">无背景音乐</option>
              {(resources?.bgm || []).filter((item) => item.id !== "bgm-none").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-zinc-400">音量
            <input type="range" min="0" max="100" step="1" value={settings.bgmVolume} onChange={(event) => setSettings((current) => ({ ...current, bgmVolume: Number(event.target.value) }))} />
            <span className="w-8 text-right">{settings.bgmVolume}%</span>
          </label>
          <label className="flex items-center gap-1 text-xs text-zinc-400">
            <input type="checkbox" checked={settings.enableSubtitles} onChange={(event) => setSettings((current) => ({ ...current, enableSubtitles: event.target.checked }))} />字幕
          </label>
          <button type="button" disabled={settingsBusy} onClick={() => void saveSettings()} className="ml-auto flex items-center gap-1 border border-zinc-700 px-3 py-1 text-xs text-zinc-200 disabled:opacity-40"><Save className="h-3.5 w-3.5" />{settingsBusy ? "保存中" : "保存设置"}</button>
        </div>
      </section>
      {selectedSceneIds.size > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 bg-zinc-950 px-3 py-2">
          <span className="text-xs text-zinc-300">选中 {selectedSceneIds.size} 项</span>
          <input value={batchPrefix} onChange={(event) => setBatchPrefix(event.target.value)} placeholder="提示词前缀" className="min-w-40 flex-1 border border-zinc-800 bg-black px-2 py-1 text-xs text-zinc-200" />
          <button type="button" disabled={batchBusy} onClick={() => void submitBatch()} className="bg-amber-500 px-3 py-1 text-xs font-semibold text-black disabled:opacity-40">批量重新生成</button>
        </div>
      )}
      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(190px,240px)_minmax(0,1fr)] 2xl:grid-cols-[minmax(190px,240px)_minmax(0,1fr)_minmax(280px,360px)]">
        <SceneList className={mobilePanel === "scenes" ? "flex" : "hidden lg:flex"} scenes={project.scenes} selectedSceneId={selectedSceneId} selectedSceneIds={selectedSceneIds} onSelect={(id) => { setSelectedSceneId(id); setMobilePanel(null); }} onToggle={toggleScene} />
        <main className={`${mobilePanel ? "hidden lg:block" : "block"} min-w-0 bg-black p-3 sm:p-6`}>
          <div className="mb-3 flex items-center justify-between">
            <div className="text-xs text-zinc-400">
              {selected ? `分镜 #${selectedIndex + 1} · ${selected.durationSeconds.toFixed(1)} 秒` : "未选择分镜"}
              <span className="ml-3 font-mono text-zinc-500">{formatTimelineTime(currentTime)} / {formatTimelineTime(totalDuration)}</span>
            </div>
            <div className="flex items-center gap-1">
              <button type="button" title="上一个分镜" aria-label="上一个分镜" onClick={() => goToAdjacentScene(-1)} className="p-2 text-zinc-400 disabled:opacity-30" disabled={!currentSceneItem && !currentSceneItemRef.current}><SkipBack className="h-4 w-4" /></button>
              <button type="button" title={isPlaying ? "暂停播放" : "播放项目"} aria-label={isPlaying ? "暂停播放" : "播放项目"} onClick={() => togglePlay()} disabled={project.scenes.length === 0} className="flex h-8 w-8 items-center justify-center bg-amber-500 text-black disabled:opacity-30">{isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</button>
              <button type="button" title="下一个分镜" aria-label="下一个分镜" onClick={() => goToAdjacentScene(1)} className="p-2 text-zinc-400 disabled:opacity-30" disabled={!currentSceneItem && !currentSceneItemRef.current}><SkipForward className="h-4 w-4" /></button>
            </div>
          </div>
          <div className="flex aspect-video items-center justify-center overflow-hidden border border-zinc-800 bg-zinc-950 text-xs text-zinc-600">
            {currentVersion ? <img src={currentVersion.imageUrl} alt="画面预览" className="h-full w-full object-contain" /> : <>画面预览{selected ? ` · #${selectedIndex + 1}` : ""}</>}
          </div>
          <audio ref={audioRef} className="hidden" preload="auto"
            onLoadedMetadata={() => {
              const audio = audioRef.current;
              const pending = lastSeekRef.current;
              if (audio && pending && audio.dataset.scene === pending.sceneId) {
                audio.currentTime = pending.localTime;
                if (isPlayingRef.current && audio.paused) audio.play().catch(() => { /* non-fatal */ });
              }
            }}
            onError={() => {
              const audio = audioRef.current;
              if (!audio) return;
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
              if (!audio || !selectedBgm?.src || !Number.isFinite(audio.duration) || audio.duration <= 0) return;
              audio.currentTime = currentTimeRef.current % audio.duration;
              if (isPlayingRef.current && audio.paused) audio.play().catch(() => { /* non-fatal */ });
            }}
            onError={() => {
              if (selectedBgm?.src && bgmErrorRef.current !== selectedBgm.src) {
                bgmErrorRef.current = selectedBgm.src;
                addToast("背景音乐加载失败，已继续播放旁白", "error");
              }
            }}
          />
        </main>
        <SceneInspector className={`${mobilePanel === "inspector" ? "block" : "hidden lg:block"} lg:col-start-2 lg:col-span-1 2xl:col-start-auto 2xl:col-span-1`} scene={selected}
          onSave={(patch) => selected ? act(() => patchScene(projectId, selected.sceneId, patch), "场景草稿已保存") : Promise.resolve()}
          onRegenerateImage={(prompt) => selected ? act(() => regenerateImage(projectId, selected.sceneId, prompt), "图片生成任务已提交") : Promise.resolve()}
          onRegenerateTts={(narration) => selected ? act(() => regenerateTts(projectId, selected.sceneId, narration), "配音生成任务已提交") : Promise.resolve()}
          onUpload={(file) => selected ? act(() => uploadSceneAsset(projectId, selected.sceneId, file), "素材已上传为候选版本") : Promise.resolve()}
          onSelectVersion={(versionId) => selected ? act(() => selectAssetVersion(projectId, selected.sceneId, versionId), "已切换当前版本") : Promise.resolve()}
        />
      </div>
      <WorkbenchTimeline scenes={project.scenes} selectedSceneId={selectedSceneId} currentTime={currentTime} totalDuration={totalDuration} isPlaying={isPlaying} pixelsPerSecond={pixelsPerSecond} canUndo={timelinePast.length > 0} canRedo={timelineFuture.length > 0} onZoomChange={(value) => setPixelsPerSecond(Math.min(120, Math.max(8, value)))} onSeek={seek} onPause={() => setIsPlaying(false)} onSelect={setSelectedSceneId} onReorder={handleTimelineReorder} onHold={handleTimelineHold} onUndo={handleUndo} onRedo={handleRedo} />
      <GenerationQueue jobs={project.jobs} />
      <ExportDialog project={project} open={exportOpen} onClose={() => setExportOpen(false)} onExport={submitExport} onLocateScene={(sceneId) => { setSelectedSceneId(sceneId); setExportOpen(false); }} />
    </div>
  );
};
