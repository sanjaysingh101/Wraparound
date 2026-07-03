import { create } from "zustand";
import { api } from "../lib/api";
import type { JobState, ProjectMeta, SystemStatus } from "../lib/types";

export type View =
  | { kind: "home" }
  | { kind: "project"; id: string }
  | { kind: "settings" };

interface AppState {
  view: View;
  projects: ProjectMeta[];
  system: SystemStatus | null;
  backendUp: boolean;
  error: string | null;

  navigate: (view: View) => void;
  setError: (message: string | null) => void;
  refreshProjects: () => Promise<void>;
  refreshSystem: () => Promise<void>;
  updateProject: (meta: ProjectMeta) => void;
  applyJobUpdate: (job: JobState) => void;
}

export const useApp = create<AppState>((set, get) => ({
  view: { kind: "home" },
  projects: [],
  system: null,
  backendUp: false,
  error: null,

  navigate: (view) => set({ view }),
  setError: (error) => set({ error }),

  refreshProjects: async () => {
    try {
      const projects = await api.listProjects();
      set({ projects, backendUp: true });
    } catch {
      set({ backendUp: false });
    }
  },

  refreshSystem: async () => {
    try {
      const system = await api.systemStatus();
      set({ system, backendUp: true });
    } catch {
      set({ backendUp: false });
    }
  },

  updateProject: (meta) =>
    set({ projects: get().projects.map((p) => (p.id === meta.id ? meta : p)) }),

  applyJobUpdate: (job) =>
    set({
      projects: get().projects.map((p) => (p.id === job.project_id ? { ...p, job } : p)),
    }),
}));
