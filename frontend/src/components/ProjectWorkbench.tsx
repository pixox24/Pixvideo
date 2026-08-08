import React, { useEffect, useMemo, useRef, useState } from "react";
import { Download, List, Music, PanelRight, Pause, Play, RefreshCw, Save, SkipBack, SkipForward } from "lucide-react";
import { GenerationRun, Project, WorkbenchResources } from "../types";
import { cancelGenerationRun, createExport, fetchActiveGenerationRun, fetchGenerationRun, fetchProject, patchProject, pauseGenerationRun, patchScene, regenerateImage, regenerateTts, retryExport, retryFailedGeneration, resumeGenerationRun, selectAssetVersion, startGenerationRun, submitBatchImageGeneration, updateTimeline, uploadSceneAsset } from "../lib/workbenchApi";
import { initialGenerationState, reduceRunActionFailed, reduceRunActionFinished, reduceRunFetched, reduceRunStarted, ProjectGenerationState, shouldRefreshProject } from "../lib/projectGenerationState";
import { SceneList } from "./SceneList";
import { SceneInspector } from "./SceneInspector";
import { GenerationQueue } from "./GenerationQueue";
import { WorkbenchTimeline } from "./WorkbenchTimeline";
import { ExportDialog } from "./ExportDialog";
import { GenerationRunPanel } from "./GenerationRunPanel";

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
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [audioPlaying, setAudioPlaying] = useState(false);
  const latestRunRef = useRef<GenerationRun | null>(null);

  const load = async () => { try { const next = await fetchProject(projectId); setProject(next); setSelectedSceneId((current) => current || next.scenes[0]?.sceneId || null); } catch (error) { addToast(error, "error"); } };
  useEffect(() => {
    latestRunRef.current = null;
    setGeneration(initialGenerationState);
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

  const selected = useMemo(() => project?.scenes.find((scene) => scene.sceneId === selectedSceneId) || null, [project, selectedSceneId]);
  const selectedIndex = selected && project ? project.scenes.findIndex((scene) => scene.sceneId === selected.sceneId) : -1;
  useEffect(() => {
    audioRef.current?.pause();
    if (audioRef.current) audioRef.current.currentTime = 0;
    setAudioPlaying(false);
  }, [selectedSceneId]);
  const act = async (action: () => Promise<unknown>, message: string) => { try { await action(); addToast(message, "success"); await load(); } catch (error) { addToast(error, "error"); throw error; } };
  if (!project) return <div className="p-6 text-sm text-zinc-400">正在加载项目…</div>;
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
  const selectAdjacentScene = (offset: number) => {
    if (!project || !selectedSceneId) return;
    const index = project.scenes.findIndex((scene) => scene.sceneId === selectedSceneId);
    const next = project.scenes[index + offset];
    if (next) setSelectedSceneId(next.sceneId);
  };
  const toggleAudio = async () => {
    if (!audioRef.current) return;
    if (audioPlaying) { audioRef.current.pause(); setAudioPlaying(false); return; }
    try { await audioRef.current.play(); setAudioPlaying(true); } catch (error) { addToast(error, "error"); }
  };
  const pendingCount = project.scenes.filter((scene) => scene.generationState?.image !== "ready" || scene.generationState?.audio !== "ready").length;
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
  return <div className="flex min-h-[640px] flex-col overflow-hidden border border-zinc-800 bg-[#101114]"><GenerationRunPanel run={generation.run} busy={generation.actionBusy} pendingCount={pendingCount} onStart={startRun} onPause={() => generation.run && void runAction("pause", () => pauseGenerationRun(projectId, generation.run!.runId))} onResume={() => generation.run && void runAction("resume", () => resumeGenerationRun(projectId, generation.run!.runId))} onCancel={() => generation.run && void runAction("cancel", () => cancelGenerationRun(projectId, generation.run!.runId))} onRetry={() => generation.run && void runAction("retry", () => retryFailedGeneration(projectId, generation.run!.runId))} />
    <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-3"><div className="min-w-0"><div className="truncate text-sm font-semibold text-zinc-100">{project.title}</div><div className="text-[10px] text-zinc-500">AI 剪辑工作台 · {project.scenes.length} 个分镜{statusLabel ? ` · ${statusLabel}` : ""}</div></div><div className="flex items-center gap-1">{project.latestExport?.status === "failed" && <button type="button" onClick={() => void retryInitialExport()} className="flex items-center gap-1 border border-red-900 px-3 py-2 text-xs text-red-300"><RefreshCw className="h-3.5 w-3.5" />重试初稿</button>}{project.latestExport?.outputUrl && <a href={project.latestExport.outputUrl} target="_blank" rel="noreferrer" className="flex items-center gap-1 border border-zinc-700 px-3 py-2 text-xs text-zinc-200"><Play className="h-3.5 w-3.5" />查看初稿</a>}<button type="button" aria-label="打开分镜面板" onClick={() => setMobilePanel(mobilePanel === "scenes" ? null : "scenes")} className="p-2 text-zinc-400 lg:hidden"><List className="h-4 w-4" /></button><button type="button" aria-label="打开检查器" onClick={() => setMobilePanel(mobilePanel === "inspector" ? null : "inspector")} className="p-2 text-zinc-400 lg:hidden"><PanelRight className="h-4 w-4" /></button><button type="button" onClick={() => setExportOpen(true)} className="flex items-center gap-1 bg-amber-500 px-3 py-2 text-xs font-semibold text-black"><Download className="h-3.5 w-3.5" />导出</button><button type="button" title="刷新项目" aria-label="刷新项目" onClick={() => void load()} className="p-2 text-zinc-400 hover:text-zinc-100"><RefreshCw className="h-4 w-4" /></button></div></div>
    <section className="border-b border-zinc-800 bg-[#0d0e11] px-3 py-2"><div className="flex flex-wrap items-center gap-3"><Music className="h-4 w-4 text-zinc-500" /><label className="flex items-center gap-2 text-xs text-zinc-400">BGM<select value={settings.bgm} onChange={(event) => setSettings((current) => ({ ...current, bgm: event.target.value }))} className="border border-zinc-800 bg-black px-2 py-1 text-xs text-zinc-200"><option value="bgm-none">无背景音乐</option>{(resources?.bgm || []).filter((item) => item.id !== "bgm-none").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="flex items-center gap-2 text-xs text-zinc-400">音量<input type="range" min="0" max="100" step="1" value={settings.bgmVolume} onChange={(event) => setSettings((current) => ({ ...current, bgmVolume: Number(event.target.value) }))} /><span className="w-8 text-right">{settings.bgmVolume}%</span></label><label className="flex items-center gap-1 text-xs text-zinc-400"><input type="checkbox" checked={settings.enableSubtitles} onChange={(event) => setSettings((current) => ({ ...current, enableSubtitles: event.target.checked }))} />字幕</label><button type="button" disabled={settingsBusy} onClick={() => void saveSettings()} className="ml-auto flex items-center gap-1 border border-zinc-700 px-3 py-1 text-xs text-zinc-200 disabled:opacity-40"><Save className="h-3.5 w-3.5" />{settingsBusy ? "保存中" : "保存设置"}</button></div></section>
    {selectedSceneIds.size > 0 && <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 bg-zinc-950 px-3 py-2"><span className="text-xs text-zinc-300">选中 {selectedSceneIds.size} 项</span><input value={batchPrefix} onChange={(event) => setBatchPrefix(event.target.value)} placeholder="提示词前缀" className="min-w-40 flex-1 border border-zinc-800 bg-black px-2 py-1 text-xs text-zinc-200" /><button type="button" disabled={batchBusy} onClick={() => void submitBatch()} className="bg-amber-500 px-3 py-1 text-xs font-semibold text-black disabled:opacity-40">批量重新生成</button></div>}
    <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(190px,240px)_minmax(0,1fr)_minmax(280px,360px)]"><SceneList className={mobilePanel === "scenes" ? "flex" : "hidden lg:flex"} scenes={project.scenes} selectedSceneId={selectedSceneId} selectedSceneIds={selectedSceneIds} onSelect={(id) => { setSelectedSceneId(id); setMobilePanel(null); }} onToggle={toggleScene} /><main className={`${mobilePanel ? "hidden lg:block" : "block"} min-w-0 bg-black p-3 sm:p-6`}><div className="mb-3 flex items-center justify-between"><div className="text-xs text-zinc-400">{selected ? `分镜 #${selectedIndex + 1} · ${selected.durationSeconds.toFixed(1)} 秒` : "未选择分镜"}</div><div className="flex items-center gap-1"><button type="button" title="上一个分镜" aria-label="上一个分镜" onClick={() => selectAdjacentScene(-1)} className="p-2 text-zinc-400 disabled:opacity-30" disabled={selectedIndex <= 0}><SkipBack className="h-4 w-4" /></button><button type="button" title={audioPlaying ? "暂停旁白" : "播放旁白"} aria-label={audioPlaying ? "暂停旁白" : "播放旁白"} onClick={() => void toggleAudio()} disabled={!selected?.audioUrl} className="flex h-8 w-8 items-center justify-center bg-amber-500 text-black disabled:opacity-30">{audioPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</button><button type="button" title="下一个分镜" aria-label="下一个分镜" onClick={() => selectAdjacentScene(1)} className="p-2 text-zinc-400 disabled:opacity-30" disabled={selectedIndex < 0 || selectedIndex >= project.scenes.length - 1}><SkipForward className="h-4 w-4" /></button></div></div><div className="flex aspect-video items-center justify-center overflow-hidden border border-zinc-800 bg-zinc-950 text-xs text-zinc-600">{currentVersion ? <img src={currentVersion.imageUrl} alt="画面预览" className="h-full w-full object-contain" /> : <>画面预览{selected ? ` · #${selectedIndex + 1}` : ""}</>}</div>{selected?.audioUrl && <audio ref={audioRef} key={selected.sceneId} src={selected.audioUrl} controls className="mt-3 h-8 w-full" onPlay={() => setAudioPlaying(true)} onPause={() => setAudioPlaying(false)} onEnded={() => setAudioPlaying(false)} />}</main><SceneInspector className={mobilePanel === "inspector" ? "block" : "hidden lg:block"} scene={selected} onSave={(patch) => selected ? act(() => patchScene(projectId, selected.sceneId, patch), "场景草稿已保存") : Promise.resolve()} onRegenerateImage={(prompt) => selected ? act(() => regenerateImage(projectId, selected.sceneId, prompt), "图片生成任务已提交") : Promise.resolve()} onRegenerateTts={(narration) => selected ? act(() => regenerateTts(projectId, selected.sceneId, narration), "配音生成任务已提交") : Promise.resolve()} onUpload={(file) => selected ? act(() => uploadSceneAsset(projectId, selected.sceneId, file), "素材已上传为候选版本") : Promise.resolve()} onSelectVersion={(versionId) => selected ? act(() => selectAssetVersion(projectId, selected.sceneId, versionId), "已切换当前版本") : Promise.resolve()} /></div>
    <WorkbenchTimeline scenes={project.scenes} selectedSceneId={selectedSceneId} onSelect={setSelectedSceneId} onReorder={(ids) => void act(() => updateTimeline(projectId, ids, {}), "时间线顺序已保存")} onHold={(sceneId, hold) => void act(() => updateTimeline(projectId, project.scenes.map((item) => item.sceneId), { [sceneId]: hold }), "停留时长已保存")} /><GenerationQueue jobs={project.jobs} /><ExportDialog project={project} open={exportOpen} onClose={() => setExportOpen(false)} onExport={submitExport} onLocateScene={(sceneId) => { setSelectedSceneId(sceneId); setExportOpen(false); }} /></div>;
};
