import type {
  CameraKeyframe,
  ExportFormatInfo,
  ExportRecord,
  Flyaround,
  JobState,
  PipelineConfig,
  ProjectMeta,
  SystemStatus,
  ValidationReport,
} from "./types";

export const API_BASE = "http://127.0.0.1:7345";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // system
  systemStatus: () => request<SystemStatus>("/api/system/status"),
  health: () => request<{ ok: boolean }>("/api/system/health"),

  // projects
  listProjects: () => request<ProjectMeta[]>("/api/projects"),
  createProject: (name: string) =>
    request<ProjectMeta>("/api/projects", { method: "POST", body: JSON.stringify({ name }) }),
  getProject: (id: string) => request<ProjectMeta>(`/api/projects/${id}`),
  duplicateProject: (id: string) =>
    request<ProjectMeta>(`/api/projects/${id}/duplicate`, { method: "POST" }),
  deleteProject: (id: string) => request<{ deleted: string }>(`/api/projects/${id}`, { method: "DELETE" }),
  updateConfig: (id: string, config: PipelineConfig) =>
    request<ProjectMeta>(`/api/projects/${id}/config`, {
      method: "PUT",
      body: JSON.stringify({ config }),
    }),

  uploadVideo: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ValidationReport>(`/api/projects/${id}/video`, { method: "POST", body: form });
  },
  registerVideoPath: (id: string, path: string) =>
    request<ValidationReport>(`/api/projects/${id}/video/path`, {
      method: "POST",
      body: JSON.stringify({ path }),
    }),

  // jobs
  startJob: (id: string, opts: { resume?: boolean; retrain?: boolean } = {}) =>
    request<JobState>(`/api/projects/${id}/job`, {
      method: "POST",
      body: JSON.stringify({ resume: true, retrain: false, ...opts }),
    }),
  cancelJob: (id: string) => request<unknown>(`/api/projects/${id}/job`, { method: "DELETE" }),
  jobState: (id: string) => request<JobState | null>(`/api/projects/${id}/job`),

  // fly-arounds
  addFlyaround: (
    id: string,
    body: { name: string; keyframes: CameraKeyframe[]; duration: number; loop: boolean },
  ) =>
    request<Flyaround[]>(`/api/projects/${id}/flyarounds`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteFlyaround: (id: string, flyaroundId: string) =>
    request<Flyaround[]>(`/api/projects/${id}/flyarounds/${flyaroundId}`, { method: "DELETE" }),

  // exports
  exportFormats: (id: string) => request<ExportFormatInfo[]>(`/api/projects/${id}/exports/formats`),
  listExports: (id: string) => request<ExportRecord[]>(`/api/projects/${id}/exports`),
  createExport: (id: string, format: string) =>
    request<ExportRecord>(`/api/projects/${id}/exports`, {
      method: "POST",
      body: JSON.stringify({ format }),
    }),

  // settings
  getSettings: () => request<Record<string, unknown>>("/api/settings"),
  patchSettings: (patch: Record<string, unknown>) =>
    request<Record<string, unknown>>("/api/settings", { method: "PATCH", body: JSON.stringify(patch) }),
};

export const projectFileUrl = (projectId: string, relPath: string) =>
  `${API_BASE}/api/projects/${projectId}/files/${relPath}`;

export const exportDownloadUrl = (projectId: string, file: string) =>
  `${API_BASE}/api/projects/${projectId}/exports/download/${file.replace(/^exports\//, "")}`;

export function jobSocket(projectId: string): WebSocket {
  return new WebSocket(`${API_BASE.replace("http", "ws")}/api/ws/projects/${projectId}`);
}
