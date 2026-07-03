import { Check, CircleDashed, Loader2, SkipForward, X } from "lucide-react";
import type { ProjectMeta, StageState } from "../lib/types";
import { STAGE_LABELS } from "../lib/types";

function fmtDuration(s: number | null | undefined): string {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

function StageIcon({ stage }: { stage: StageState }) {
  switch (stage.status) {
    case "completed":
      return <Check size={14} className="text-txt" />;
    case "skipped":
      return <SkipForward size={14} className="text-dim" />;
    case "running":
      return <Loader2 size={14} className="animate-spin text-accent" />;
    case "failed":
      return <X size={14} className="text-signal" />;
    default:
      return <CircleDashed size={14} className="text-faint" />;
  }
}

export function PipelineProgress({ project }: { project: ProjectMeta }) {
  const job = project.job;

  if (!job) {
    return (
      <div className="p-12 text-center space-y-1">
        <p className="text-[11px] uppercase tracking-wider2 text-sub">Video validated — ready</p>
        <p className="text-[11px] text-dim">Press RUN to start the reconstruction pipeline.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl p-8">
      <div className="mb-5 flex items-baseline justify-between">
        <div className="text-[10px] uppercase tracking-wider2 text-dim">
          Elapsed <span className="text-txt tabular-nums">{fmtDuration(job.elapsed_s)}</span>
        </div>
        <div className="text-[10px] uppercase tracking-wider2 text-dim">
          Remaining{" "}
          <span className="text-txt tabular-nums">
            {job.status === "running" ? `≈ ${fmtDuration(job.eta_s)}` : "—"}
          </span>
        </div>
      </div>

      <ol className="space-y-1">
        {job.stages.map((stage, i) => (
          <li key={stage.name} className={`card px-4 py-3 ${stage.status === "running" ? "border-accent/40" : ""}`}>
            <div className="flex items-center gap-3">
              <span className="text-[10px] tabular-nums text-faint w-5">{String(i + 1).padStart(2, "0")}</span>
              <StageIcon stage={stage} />
              <span className={`flex-1 text-[11px] uppercase tracking-wider2 ${stage.status === "pending" ? "text-dim" : "text-txt"}`}>
                {STAGE_LABELS[stage.name]}
              </span>
              {stage.status === "running" && (
                <span className="text-[10px] tabular-nums text-sub">{Math.round(stage.progress * 100)}%</span>
              )}
            </div>
            {stage.status === "running" && (
              <>
                <div className="mt-2 h-0.5 overflow-hidden bg-white/10">
                  <div className="h-full bg-accent transition-all duration-300" style={{ width: `${stage.progress * 100}%` }} />
                </div>
                {stage.message && <p className="mt-1.5 truncate text-[10px] text-dim">{stage.message}</p>}
              </>
            )}
            {stage.status === "failed" && stage.error && (
              <p className="mt-2 whitespace-pre-wrap text-[10px] text-signal leading-relaxed">{stage.error}</p>
            )}
          </li>
        ))}
      </ol>

      {job.status === "failed" && !job.stages.some((s) => s.error) && job.error && (
        <div className="card mt-4 border-signal/40 p-4">
          <p className="whitespace-pre-wrap text-[11px] text-signal leading-relaxed">{job.error}</p>
        </div>
      )}
      {job.status === "completed" && (
        <p className="mt-6 text-center text-[11px] uppercase tracking-wider2 text-txt">
          Reconstruction complete — open the Viewer tab
        </p>
      )}
    </div>
  );
}
