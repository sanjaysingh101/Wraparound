import { Plus, Settings } from "lucide-react";
import { useApp } from "../state/store";
import { api } from "../lib/api";
import type { JobState } from "../lib/types";
import { DotMatrix, StatusDot } from "./ui";

function dotStatus(job?: JobState | null): "running" | "completed" | "failed" | "idle" {
  if (!job) return "idle";
  if (job.status === "running") return "running";
  if (job.status === "completed") return "completed";
  if (job.status === "failed") return "failed";
  return "idle";
}

export function Sidebar() {
  const { view, projects, system, navigate, refreshProjects, setError } = useApp();

  const newProject = async () => {
    try {
      const meta = await api.createProject(`Untitled ${projects.length + 1}`);
      await refreshProjects();
      navigate({ kind: "project", id: meta.id });
    } catch (e) {
      setError(String(e));
    }
  };

  const gpu = system?.hardware.gpus[0];

  return (
    <aside className="w-60 shrink-0 border-r border-white/10 bg-surface flex flex-col">
      {/* brand */}
      <button
        className="flex items-center gap-2.5 px-4 h-14 shrink-0"
        onClick={() => navigate({ kind: "home" })}
      >
        <DotMatrix cols={3} rows={3} size={3} gap={2} lit={[0, 4, 8, 2, 6]} />
        <span className="text-[12px] uppercase tracking-widest2 text-txt">Wraparound</span>
      </button>

      <div className="px-3">
        <button
          className="w-full h-10 flex items-center justify-center gap-2 rounded-te border border-white/10
            text-[11px] uppercase tracking-wider2 text-txt hover:border-accent/50 hover:text-accent transition-colors"
          onClick={newProject}
        >
          <Plus size={14} /> New Project
        </button>
      </div>

      <nav className="mt-6 flex-1 overflow-y-auto px-2">
        <p className="eyebrow px-2 pb-2">Projects</p>
        <div className="space-y-0.5">
          {projects.map((p) => {
            const active = view.kind === "project" && view.id === p.id;
            return (
              <button
                key={p.id}
                onClick={() => navigate({ kind: "project", id: p.id })}
                className={`group w-full flex items-center gap-2.5 h-9 px-2.5 rounded-te text-left transition-colors
                  ${active ? "bg-white/[0.06] border border-white/10" : "border border-transparent hover:bg-white/[0.03]"}`}
              >
                <StatusDot status={dotStatus(p.job)} />
                <span
                  className={`flex-1 truncate text-[11px] uppercase tracking-wider2 ${
                    active ? "text-txt" : "text-sub group-hover:text-txt"
                  }`}
                >
                  {p.name}
                </span>
                {active && <span className="text-dim text-[13px] leading-none">···</span>}
              </button>
            );
          })}
          {projects.length === 0 && (
            <p className="px-2.5 py-3 text-[11px] text-dim uppercase tracking-wider2">No projects</p>
          )}
        </div>
      </nav>

      {/* system footer */}
      <div className="border-t border-white/10 p-4 space-y-3">
        <p className="eyebrow">System</p>
        <p className="text-[11px] uppercase tracking-wider2 text-sub">
          {gpu ? gpu.name : "No CUDA GPU"}
        </p>
        {system && !system.hardware.cuda_available && (
          <p className="text-[10px] leading-relaxed text-dim">
            gpu acceleration unavailable — <span className="text-sub">training will be</span>{" "}
            {system.hardware.mps_available ? "on metal gpu" : "slow or disabled"}.
          </p>
        )}
        <button
          className={`flex items-center gap-2 text-[11px] uppercase tracking-wider2 transition-colors
            ${view.kind === "settings" ? "text-accent" : "text-sub hover:text-txt"}`}
          onClick={() => navigate({ kind: "settings" })}
        >
          <Settings size={13} /> Settings
        </button>
      </div>
    </aside>
  );
}
