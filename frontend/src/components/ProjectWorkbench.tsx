import React, { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Project } from "../types";
import { fetchProject } from "../lib/workbenchApi";
import { SceneList } from "./SceneList";
import { SceneInspector } from "./SceneInspector";
import { GenerationQueue } from "./GenerationQueue";

export const ProjectWorkbench: React.FC<{ projectId: string; addToast: (text: unknown, type: "success" | "error" | "info") => void }> = ({ projectId, addToast }) => {
  const [project, setProject] = useState<Project | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string | null>(null);
  const load = async () => { try { const next = await fetchProject(projectId); setProject(next); setSelectedSceneId((current) => current || next.scenes[0]?.sceneId || null); } catch (error) { addToast(error, "error"); } };
  useEffect(() => { void load(); }, [projectId]);
  const selected = useMemo(() => project?.scenes.find((scene) => scene.sceneId === selectedSceneId) || null, [project, selectedSceneId]);
  if (!project) return <div className="p-6 text-sm text-zinc-400">正在加载项目…</div>;
  return <div className="flex min-h-[640px] flex-col overflow-hidden border border-zinc-800 bg-[#101114]"><div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3"><div><div className="text-sm font-semibold text-zinc-100">{project.title}</div><div className="text-[10px] text-zinc-500">AI 剪辑工作台 · {project.scenes.length} 个分镜</div></div><button type="button" title="刷新项目" aria-label="刷新项目" onClick={() => void load()} className="p-2 text-zinc-400 hover:text-zinc-100"><RefreshCw className="h-4 w-4" /></button></div><div className="grid min-h-0 flex-1 grid-cols-[minmax(190px,240px)_minmax(0,1fr)_minmax(280px,360px)]"><SceneList scenes={project.scenes} selectedSceneId={selectedSceneId} onSelect={setSelectedSceneId} /><main className="min-w-0 bg-black p-6"><div className="flex aspect-video items-center justify-center border border-zinc-800 bg-zinc-950 text-xs text-zinc-600">画面预览{selected ? ` · #${selected.position + 1}` : ""}</div></main><SceneInspector scene={selected} /></div><GenerationQueue jobs={project.jobs} /></div>;
};

