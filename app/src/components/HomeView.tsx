import { Copy, Trash2 } from "lucide-react";
import { api, projectFileUrl } from "../lib/api";
import { STAGE_LABELS } from "../lib/types";
import { useApp } from "../state/store";
import { StatusDot } from "./ui";

export function HomeView() {
  const { projects, system, navigate, refreshProjects, setError } = useApp();

  const duplicate = async (id: string) => {
    try {
      await api.duplicateProject(id);
      await refreshProjects();
    } catch (e) {
      setError(String(e));
    }
  };

  const remove = async (id: string, name: string) => {
    if (!window.confirm(`Delete "${name}" and all of its data?`)) return;
    try {
      await api.deleteProject(id);
      await refreshProjects();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <h1 className="text-[15px] uppercase tracking-widest2 text-txt mb-1">Library</h1>
      <p className="text-[11px] text-dim mb-6 max-w-lg leading-relaxed">
        Capture a video orbiting your subject, then turn it into a 3D Gaussian splat — fully offline.
      </p>

      {system?.hardware.warnings.map((w) => (
        <div key={w} className="panel border-accent/25 bg-accent/[0.04] mb-4 p-3 text-[11px] text-accent/90 leading-relaxed">
          {w}
        </div>
      ))}

      <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">
        {projects.map((p) => {
          const job = p.job;
          const stage = job?.current_stage ? STAGE_LABELS[job.current_stage] : null;
          const dot = !job ? "idle" : job.status === "running" ? "running" : job.status === "completed" ? "completed" : job.status === "failed" ? "failed" : "idle";
          return (
            <div key={p.id} className="card overflow-hidden group">
              <button
                className="block w-full aspect-video bg-black/40 relative border-b border-white/10"
                onClick={() => navigate({ kind: "project", id: p.id })}
              >
                <img
                  src={projectFileUrl(p.id, "preview/thumbnail.jpg")}
                  className="h-full w-full object-cover"
                  onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                  alt=""
                />
                {job?.status === "running" && (
                  <span className="absolute bottom-2 left-2 bg-black/80 px-2 py-0.5 text-[10px] uppercase tracking-wider2 text-accent rounded-te">
                    {stage ?? "Running"}…
                  </span>
                )}
                {job?.status === "failed" && (
                  <span className="absolute bottom-2 left-2 bg-black/80 px-2 py-0.5 text-[10px] uppercase tracking-wider2 text-signal rounded-te">
                    Failed
                  </span>
                )}
              </button>
              <div className="flex items-center gap-2 px-3 h-10">
                <StatusDot status={dot as "idle"} />
                <button
                  className="flex-1 text-[11px] uppercase tracking-wider2 text-sub truncate hover:text-txt text-left"
                  onClick={() => navigate({ kind: "project", id: p.id })}
                >
                  {p.name}
                </button>
                <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button className="icon-btn h-7 w-7" title="Duplicate" onClick={() => duplicate(p.id)}>
                    <Copy size={13} />
                  </button>
                  <button className="icon-btn h-7 w-7 hover:text-signal" title="Delete" onClick={() => remove(p.id, p.name)}>
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {projects.length === 0 && (
        <div className="card p-10 text-center">
          <p className="text-[11px] uppercase tracking-wider2 text-sub mb-1">No projects yet</p>
          <p className="text-[11px] text-dim">Create one from the sidebar and upload a video to begin.</p>
        </div>
      )}
    </div>
  );
}
