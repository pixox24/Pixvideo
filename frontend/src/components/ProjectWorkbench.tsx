import React, { useEffect, useMemo, useState } from "react";
import { Download, List, PanelRight, RefreshCw } from "lucide-react";
import { GenerationRun, Project } from "../types";
import { cancelGenerationRun, createExport, fetchActiveGenerationRun, fetchGenerationRun, fetchProject, pauseGenerationRun, patchScene, regenerateImage, regenerateTts, retryFailedGeneration, resumeGenerationRun, selectAssetVersion, startGenerationRun, submitBatchImageGeneration, updateTimeline, uploadSceneAsset } from "../lib/workbenchApi";
import { initialGenerationState, reduceRunActionFailed, reduceRunActionFinished, reduceRunFetched, reduceRunStarted, ProjectGenerationState } from "../lib/projectGenerationState";
import { SceneList } from "./SceneList";
import { SceneInspector } from "./SceneInspector";
import { GenerationQueue } from "./GenerationQueue";
import { WorkbenchTimeline } from "./WorkbenchTimeline";
import { ExportDialog } from "./ExportDialog";
import { GenerationRunPanel } from "./GenerationRunPanel";

export const ProjectWorkbench: React.FC<{ projectId: string; addToast: (text: unknown, type: "success" | "error" | "info") => void }> = ({ projectId, addToast }) => {
  const [project, setProject] = useState<Project | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const [selectedSceneIds, setSelectedSceneIds] = useState<Set<string>>(new Set());
  const [batchPrefix, setBatchPrefix] = useState("");
  const [batchBusy, setBatchBusy] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [mobilePanel, setMobilePanel] = useState<"scenes" | "inspector" | null>(null);
  const [generation, setGeneration] = useState<ProjectGenerationState>(initialGenerationState);

  const load = async () => { try { const next = await fetchProject(projectId); setProject(next); setSelectedSceneId((current) => current || next.scenes[0]?.sceneId || null); } catch (error) { addToast(error, "error"); } };
  useEffect(() => {
    setGeneration(initialGenerationState);
    void (async () => {
      await load();
      try {
        const activeRun = await fetchActiveGenerationRun(projectId);
        if (activeRun) setGeneration((current) => reduceRunStarted(current, activeRun));
      } catch (error) { addToast(error, "error"); }
    })();
  }, [projectId]);
  useEffect(() => {
    const runId = generation.run?.runId;
    if (!runId || !generation.polling) return;
    let busy = false;
    const timer = window.setInterval(async () => {
      if (busy) return; busy = true;
      try { const next = await fetchGenerationRun(projectId, runId); setGeneration((current) => reduceRunFetched(current, next)); await load(); }
      catch (error) { setGeneration((current) => ({ ...current, error, polling: false })); }
      finally { busy = false; }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [projectId, generation.run?.runId, generation.polling]);

  const selected = useMemo(() => project?.scenes.find((scene) => scene.sceneId === selectedSceneId) || null, [project, selectedSceneId]);
  const act = async (action: () => Promise<unknown>, message: string) => { try { await action(); addToast(message, "success"); await load(); } catch (error) { addToast(error, "error"); throw error; } };
  if (!project) return <div className="p-6 text-sm text-zinc-400">正在加载项目…</div>;
  const currentVersion = selected?.versions.find((version) => version.versionId === selected.currentVersionId);
  const toggleScene = (sceneId: string) => setSelectedSceneIds((current) => { const next = new Set(current); if (next.has(sceneId)) next.delete(sceneId); else next.add(sceneId); return next; });
  const runAction = async (action: string, request: () => Promise<GenerationRun>) => { setGeneration((current) => ({ ...current, actionBusy: action, error: null })); try { const next = await request(); setGeneration((current) => reduceRunActionFinished(current, next)); await load(); } catch (error) { setGeneration((current) => reduceRunActionFailed(current, error)); addToast(error, "error"); } };
  const startRun = () => runAction("start", async () => { const next = await startGenerationRun(projectId); setGeneration((current) => reduceRunStarted(current, next)); return next; });
  const submitBatch = async () => { setBatchBusy(true); try { await act(() => submitBatchImageGeneration(projectId, [...selectedSceneIds], batchPrefix), "批量图片任务已提交"); } finally { setBatchBusy(false); } };
  const submitExport = async (allowIncomplete: boolean) => { const result = await createExport(projectId, allowIncomplete); setProject((current) => current ? { ...current, jobs: [...current.jobs, { jobId: result.jobId, taskId: result.taskId, kind: "export", status: result.status, progress: 0 }] } : current); addToast("导出任务已提交", "success"); };
  const pendingCount = project.scenes.filter((scene) => scene.generationState?.image !== "ready" || scene.generationState?.audio !== "ready").length;
  return <div className="flex min-h-[640px] flex-col overflow-hidden border border-zinc-800 bg-[#101114]"><GenerationRunPanel run={generation.run} busy={generation.actionBusy} pendingCount={pendingCount} onStart={startRun} onPause={() => generation.run && void runAction("pause", () => pauseGenerationRun(projectId, generation.run!.runId))} onResume={() => generation.run && void runAction("resume", () => resumeGenerationRun(projectId, generation.run!.runId))} onCancel={() => generation.run && void runAction("cancel", () => cancelGenerationRun(projectId, generation.run!.runId))} onRetry={() => generation.run && void runAction("retry", () => retryFailedGeneration(projectId, generation.run!.runId))} />
    <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-3"><div className="min-w-0"><div className="truncate text-sm font-semibold text-zinc-100">{project.title}</div><div className="text-[10px] text-zinc-500">AI 剪辑工作台 · {project.scenes.length} 个分镜</div></div><div className="flex items-center gap-1"><button type="button" aria-label="打开分镜面板" onClick={() => setMobilePanel(mobilePanel === "scenes" ? null : "scenes")} className="p-2 text-zinc-400 lg:hidden"><List className="h-4 w-4" /></button><button type="button" aria-label="打开检查器" onClick={() => setMobilePanel(mobilePanel === "inspector" ? null : "inspector")} className="p-2 text-zinc-400 lg:hidden"><PanelRight className="h-4 w-4" /></button><button type="button" onClick={() => setExportOpen(true)} className="flex items-center gap-1 bg-amber-500 px-3 py-2 text-xs font-semibold text-black"><Download className="h-3.5 w-3.5" />导出</button><button type="button" title="刷新项目" aria-label="刷新项目" onClick={() => void load()} className="p-2 text-zinc-400 hover:text-zinc-100"><RefreshCw className="h-4 w-4" /></button></div></div>
    {selectedSceneIds.size > 0 && <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 bg-zinc-950 px-3 py-2"><span className="text-xs text-zinc-300">选中 {selectedSceneIds.size} 项</span><input value={batchPrefix} onChange={(event) => setBatchPrefix(event.target.value)} placeholder="提示词前缀" className="min-w-40 flex-1 border border-zinc-800 bg-black px-2 py-1 text-xs text-zinc-200" /><button type="button" disabled={batchBusy} onClick={() => void submitBatch()} className="bg-amber-500 px-3 py-1 text-xs font-semibold text-black disabled:opacity-40">批量重新生成</button></div>}
    <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(190px,240px)_minmax(0,1fr)_minmax(280px,360px)]"><SceneList className={mobilePanel === "scenes" ? "flex" : "hidden lg:flex"} scenes={project.scenes} selectedSceneId={selectedSceneId} selectedSceneIds={selectedSceneIds} onSelect={(id) => { setSelectedSceneId(id); setMobilePanel(null); }} onToggle={toggleScene} /><main className={`${mobilePanel ? "hidden lg:block" : "block"} min-w-0 bg-black p-3 sm:p-6`}><div className="flex aspect-video items-center justify-center overflow-hidden border border-zinc-800 bg-zinc-950 text-xs text-zinc-600">{currentVersion ? <img src={currentVersion.imageUrl} alt="画面预览" className="h-full w-full object-contain" /> : <>画面预览{selected ? ` · #${selected.position + 1}` : ""}</>}</div></main><SceneInspector className={mobilePanel === "inspector" ? "block" : "hidden lg:block"} scene={selected} onSave={(patch) => selected ? act(() => patchScene(projectId, selected.sceneId, patch), "场景草稿已保存") : Promise.resolve()} onRegenerateImage={(prompt) => selected ? act(() => regenerateImage(projectId, selected.sceneId, prompt), "图片生成任务已提交") : Promise.resolve()} onRegenerateTts={(narration) => selected ? act(() => regenerateTts(projectId, selected.sceneId, narration), "配音生成任务已提交") : Promise.resolve()} onUpload={(file) => selected ? act(() => uploadSceneAsset(projectId, selected.sceneId, file), "素材已上传为候选版本") : Promise.resolve()} onSelectVersion={(versionId) => selected ? act(() => selectAssetVersion(projectId, selected.sceneId, versionId), "已切换当前版本") : Promise.resolve()} /></div>
    <WorkbenchTimeline scenes={project.scenes} selectedSceneId={selectedSceneId} onSelect={setSelectedSceneId} onReorder={(ids) => void act(() => updateTimeline(projectId, ids, {}), "时间线顺序已保存")} onHold={(sceneId, hold) => void act(() => updateTimeline(projectId, project.scenes.map((item) => item.sceneId), { [sceneId]: hold }), "停留时长已保存")} /><GenerationQueue jobs={project.jobs} /><ExportDialog project={project} open={exportOpen} onClose={() => setExportOpen(false)} onExport={submitExport} onLocateScene={(sceneId) => { setSelectedSceneId(sceneId); setExportOpen(false); }} /></div>;
};
