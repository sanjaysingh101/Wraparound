import { useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Film, XCircle } from "lucide-react";
import { api } from "../lib/api";
import type { ProjectMeta, ValidationReport } from "../lib/types";
import { useApp } from "../state/store";

export function UploadPanel({ project }: { project: ProjectMeta }) {
  const { refreshProjects, setError } = useApp();
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<ValidationReport | null>(project.validation ?? null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleFile = async (file: File) => {
    setBusy(true);
    setReport(null);
    try {
      const r = await api.uploadVideo(project.id, file);
      setReport(r);
      await refreshProjects();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const rejects = report?.issues.filter((i) => i.severity === "reject") ?? [];
  const warns = report?.issues.filter((i) => i.severity === "warn") ?? [];

  return (
    <div className="mx-auto max-w-2xl p-8 space-y-5">
      <div
        className={`card flex flex-col items-center justify-center gap-3 border-2 border-dashed p-12 text-center transition-colors
          ${dragging ? "border-accent/60 bg-accent/[0.04]" : "border-white/15"}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) void handleFile(f); }}
      >
        <Film size={32} className="text-dim" />
        {busy ? (
          <p className="animate-pulse text-[11px] uppercase tracking-wider2 text-sub">Analyzing capture…</p>
        ) : (
          <>
            <p className="text-[12px] text-sub">
              Drop a video, or{" "}
              <button className="text-accent hover:underline uppercase tracking-wider2 text-[11px]" onClick={() => fileInput.current?.click()}>
                browse
              </button>
            </p>
            <p className="text-[10px] uppercase tracking-wider2 text-dim">
              MP4 · MOV · M4V — orbit slowly, 20–60s
            </p>
          </>
        )}
        <input ref={fileInput} type="file" accept=".mp4,.mov,.m4v,video/mp4,video/quicktime" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void handleFile(f); }} />
      </div>

      {report && (
        <div className="card p-5 space-y-4">
          <div className="flex items-center gap-2">
            {rejects.length === 0 ? (
              <>
                <CheckCircle2 className="text-txt" size={16} />
                <span className="text-[11px] uppercase tracking-wider2 text-txt">
                  Capture looks {warns.length ? "usable" : "good"} — ready
                </span>
              </>
            ) : (
              <>
                <XCircle className="text-signal" size={16} />
                <span className="text-[11px] uppercase tracking-wider2 text-signal">Unsuitable capture</span>
              </>
            )}
          </div>

          <div className="grid grid-cols-4 gap-2">
            {[
              ["Sharpness", report.sharpness.toFixed(0)],
              ["Brightness", report.brightness.toFixed(0)],
              ["Shake", report.shakiness.toFixed(1)],
              ["Parallax", report.motion_coverage.toFixed(1)],
            ].map(([label, value]) => (
              <div key={label} className="bg-black/40 border border-white/10 rounded-te py-2 text-center">
                <div className="text-[14px] text-txt tabular-nums">{value}</div>
                <div className="eyebrow mt-0.5">{label}</div>
              </div>
            ))}
          </div>

          {[...rejects, ...warns].map((issue) => (
            <div key={issue.code} className="flex items-start gap-2 text-[11px]">
              {issue.severity === "reject" ? (
                <XCircle size={14} className="mt-0.5 shrink-0 text-signal" />
              ) : (
                <AlertTriangle size={14} className="mt-0.5 shrink-0 text-accent" />
              )}
              <p className="text-sub leading-relaxed">{issue.message}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
