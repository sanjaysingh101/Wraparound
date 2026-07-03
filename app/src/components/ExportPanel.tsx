import { useEffect, useState } from "react";
import { Download, PackageOpen } from "lucide-react";
import { api, exportDownloadUrl } from "../lib/api";
import type { ExportFormatInfo, ProjectMeta } from "../lib/types";
import { useApp } from "../state/store";

const FORMAT_HINTS: Record<string, string> = {
  ply: "Standard 3DGS point cloud — widest tool compatibility (SuperSplat, Blender…)",
  splat: "Compact web format (antimatter15) — great for three.js / web viewers",
  ksplat: "Optimized format for @mkkellogg/gaussian-splats-3d — fastest web loading",
};

function fmtBytes(n: number): string {
  if (n > 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.round(n / 1e3)} KB`;
}

export function ExportPanel({ project }: { project: ProjectMeta }) {
  const { refreshProjects, setError } = useApp();
  const [formats, setFormats] = useState<ExportFormatInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const trained = project.job?.status === "completed";

  useEffect(() => {
    api.exportFormats(project.id).then(setFormats).catch(() => {});
  }, [project.id]);

  const doExport = async (format: string) => {
    setBusy(format);
    try {
      await api.createExport(project.id, format);
      await refreshProjects();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-8">
      <div className="grid gap-2.5">
        {formats.map((f) => (
          <div key={f.format} className="card flex items-center gap-4 p-4">
            <PackageOpen size={18} className="shrink-0 text-dim" />
            <div className="min-w-0 flex-1">
              <div className="text-[12px] uppercase tracking-wider2 text-txt">{f.format}</div>
              <p className="text-[10px] text-dim mt-0.5 leading-relaxed">{FORMAT_HINTS[f.format] ?? ""}</p>
              {!f.available && <p className="mt-1 text-[10px] text-accent">{f.reason}</p>}
            </div>
            <button className="btn-primary" disabled={!f.available || !trained || busy !== null} onClick={() => doExport(f.format)}>
              {busy === f.format ? "Exporting…" : "Export"}
            </button>
          </div>
        ))}
      </div>

      {!trained && (
        <p className="text-center text-[11px] uppercase tracking-wider2 text-dim">
          Exports available once training completes
        </p>
      )}

      {project.exports.length > 0 && (
        <div>
          <p className="eyebrow mb-2 px-1">Previous exports</p>
          <div className="card divide-y divide-white/10">
            {[...project.exports].reverse().map((e) => (
              <div key={e.file} className="flex items-center gap-3 px-4 h-11 text-[11px]">
                <span className="flex-1 truncate text-sub">{e.file.replace("exports/", "")}</span>
                <span className="text-[10px] tabular-nums text-dim">{fmtBytes(e.bytes)}</span>
                <a className="text-accent hover:text-txt" href={exportDownloadUrl(project.id, e.file)} download>
                  <Download size={14} />
                </a>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
