export type RecentProject = {
  projectId: string;
  title: string;
  updatedAt: string;
};

const RECENT_PROJECTS_KEY = "pixvideo.recent-projects.v1";
const MAX_RECENT = 8;

export function loadRecentProjects(): RecentProject[] {
  try {
    const raw = localStorage.getItem(RECENT_PROJECTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (item): item is RecentProject =>
          Boolean(item) &&
          typeof item === "object" &&
          typeof item.projectId === "string" &&
          typeof item.title === "string" &&
          typeof item.updatedAt === "string",
      )
      .slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

export function pushRecentProject(project: RecentProject): RecentProject[] {
  const next = [
    project,
    ...loadRecentProjects().filter((item) => item.projectId !== project.projectId),
  ].slice(0, MAX_RECENT);
  try {
    localStorage.setItem(RECENT_PROJECTS_KEY, JSON.stringify(next));
  } catch {
    /* ignore quota */
  }
  return next;
}

export function removeRecentProject(projectId: string): RecentProject[] {
  const next = loadRecentProjects().filter((item) => item.projectId !== projectId);
  try {
    localStorage.setItem(RECENT_PROJECTS_KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
  return next;
}
