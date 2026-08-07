import React from "react";
import { GenerationJob } from "../types";
export const GenerationQueue: React.FC<{ jobs: GenerationJob[] }> = ({ jobs }) => <section className="border-t border-zinc-800 bg-[#0d0e11] p-3"><div className="mb-2 text-[10px] font-semibold uppercase text-zinc-500">GenerationQueue</div><div className="flex gap-2 overflow-x-auto">{jobs.length === 0 ? <span className="text-xs text-zinc-600">暂无生成任务</span> : jobs.map((job) => <div key={job.jobId} className="min-w-40 border border-zinc-800 px-2 py-1 text-xs text-zinc-300">{job.kind} · {job.status} · {Math.round(job.progress)}%</div>)}</div></section>;

