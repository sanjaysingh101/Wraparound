import { useEffect, useMemo, useState } from "react";
import { Copy, Play, RotateCcw, Square, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useJobSocket } from "../lib/useJobSocket";
import { useApp } from "../state/store";
import { UploadPanel } from "./UploadPanel";
import { PipelineProgress } from "./PipelineProgress";
import { SplatViewer } from "./SplatViewer";
import { SourcePanel } from "./SourcePanel";
import { ExportPanel } from "./ExportPanel";
import { ConfigPanel } from "./ConfigPanel";
import { DotMatrix } from "./ui";

type Tab = "pipeline" | "source" | "viewer" | "exports" | "config";

const TABS: [Tab, string][] = [
  ["pipeline", "Pipeline"],
  ["source", "Source"],
  ["viewer", "Viewer"],
  ["exports", "Export"],
  ["config", "Config"],
];

export function ProjectView({ projectId }: { projectId: string }) {
  const { projects, refreshProjects, setError } = useApp();
  const project = useMemo(() => projects.find((p) => p.id === projectId), [projects, projectId]);
  const [tab, setTab] = useState<Tab>("pipeline");
  const [menuOpen, setMenuOpen] = useState(false);
  useJobSocket(projectId);

  useEffect(() => {
    setTab("pipeline");
  }, [projectId]);

  useEffect(() => {
    if (project?.job?.status === "completed" && tab === "pipeline") setTab("viewer");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project?.job?.status]);

  if (!project) return <div className="p-8 text-dim uppercase tracking-wider2 text-[11px]">Project not found</div>;

  const job = project.job;
  const running = job?.status === "running";
  const trained = job?.status === "completed";
  const v = project.validation?.video;

  const start = async (retrain = false) => {
    try {
      await api.startJob(projectId, { retrain });
      await refreshProjects();
      setTab("pipeline");
    } catch (e) {
      setError(String(e));
    }
  };
  const cancel = async () => {
    try {
      await api.cancelJob(projectId);
    } catch (e) {
      setError(String(e));
    }
  };
  const duplicate = async () => {
    setMenuOpen(false);
    try {
      await api.duplicateProject(projectId);
      await refreshProjects();
    } catch (e) {
      setError(String(e));
    }
  };
  const remove = async () => {
    setMenuOpen(false);
    if (!window.confirm(`Delete "${project.name}"?`)) return;
    try {
      await api.deleteProject(projectId);
      await refreshProjects();
      useApp.getState().navigate({ kind: "home" });
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* header */}
      <header className="flex items-center gap-5 px-6 h-14 shrink-0 border-b border-white/10">
        <DotMatrix cols={7} rows={5} size={2.5} gap={3}
          lit={[1, 3, 8, 10, 12, 16, 22, 24, 30]} className="shrink-0" />
        <div className="min-w-0">
          <h1 className="text-[13px] uppercase tracking-wider2 text-txt truncate">{project.name}</h1>
          <p className="text-[10px] uppercase tracking-wider2 text-dim tabular-nums">
            {v ? `${v.width}×${v.height} · ${v.duration_s.toFixed(1)}s · ${v.fps} fps` : "no video"}
          </p>
        </div>

        <div className="ml-auto flex items-center gap-1">
          {running ? (
            <button className="btn border-signal/40 text-signal hover:bg-signal/10" onClick={cancel}>
              <Square size={13} /> Stop
            </button>
          ) : (
            <>
              {project.video_file && (
                <button className="btn-ghost px-2" onClick={() => start(false)}>
                  <Play size={14} /> {job?.status === "failed" ? "Resume" : trained ? "Re-run" : "Run"}
                </button>
              )}
              {trained && (
                <button className="btn-ghost px-2" onClick={() => start(true)}>
                  <RotateCcw size={13} /> Retrain
                </button>
              )}
            </>
          )}
          <div className="relative">
            <button className="btn-ghost px-2" onClick={() => setMenuOpen((o) => !o)}>
              Menu <span className="text-[13px] leading-none">···</span>
            </button>
            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                <div className="absolute right-0 top-9 z-20 w-40 panel py-1">
                  <button className="w-full flex items-center gap-2 px-3 h-8 text-[11px] uppercase tracking-wider2 text-sub hover:text-txt hover:bg-white/5" onClick={duplicate}>
                    <Copy size={13} /> Duplicate
                  </button>
                  <button className="w-full flex items-center gap-2 px-3 h-8 text-[11px] uppercase tracking-wider2 text-signal hover:bg-signal/10" onClick={remove}>
                    <Trash2 size={13} /> Delete
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {/* tabs */}
      <div className="flex gap-6 px-6 h-11 items-center border-b border-white/10 shrink-0">
        {TABS.map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)}
            className={`tab ${tab === key ? "tab-active" : ""}`}>
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === "pipeline" &&
          (!project.video_file ? <UploadPanel project={project} /> : <div className="h-full overflow-y-auto"><PipelineProgress project={project} /></div>)}
        {tab === "source" && <div className="h-full overflow-y-auto"><SourcePanel project={project} /></div>}
        {tab === "viewer" && <SplatViewer project={project} />}
        {tab === "exports" && <div className="h-full overflow-y-auto"><ExportPanel project={project} /></div>}
        {tab === "config" && <div className="h-full overflow-y-auto"><ConfigPanel project={project} /></div>}
      </div>
    </div>
  );
}
