import { useEffect, useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { api } from "../lib/api";
import { useApp } from "../state/store";
import { Switch } from "./ui";

const FIELDS: { key: string; label: string; type: "text" | "number" | "bool"; hint?: string }[] = [
  { key: "projects_dir", label: "Output directory", type: "text", hint: "Empty = default app-data location" },
  { key: "cache_dir", label: "Cache location", type: "text" },
  { key: "temp_dir", label: "Temporary storage", type: "text" },
  { key: "ffmpeg_path", label: "FFmpeg path", type: "text" },
  { key: "colmap_path", label: "COLMAP path", type: "text" },
  { key: "gpu_index", label: "GPU index", type: "number" },
  { key: "cpu_threads", label: "CPU threads (0 = auto)", type: "number" },
  { key: "frame_quality", label: "Frame quality (60–100)", type: "number" },
  { key: "auto_save", label: "Auto-save projects", type: "bool" },
  { key: "auto_delete_intermediates", label: "Auto-delete intermediates", type: "bool" },
];

export function SettingsView() {
  const { system, setError, refreshSystem } = useApp();
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getSettings().then(setValues).catch((e) => setError(String(e)));
  }, [setError]);

  const save = async () => {
    const patch: Record<string, unknown> = {};
    for (const f of FIELDS) patch[f.key] = values[f.key] === "" ? null : values[f.key];
    try {
      setValues(await api.patchSettings(patch));
      setDirty(false);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2000);
      await refreshSystem();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5 p-8">
      <h1 className="text-[15px] uppercase tracking-widest2 text-txt">Settings</h1>

      <section className="card p-5">
        <h3 className="eyebrow mb-3">Hardware</h3>
        {system && (
          <div className="space-y-1 text-[11px] text-sub leading-relaxed">
            <p>{system.hardware.platform}</p>
            <p className="tabular-nums">
              {system.hardware.cpu_cores} cores · {(system.hardware.ram_mb / 1024).toFixed(0)} GB RAM
              {system.hardware.torch_version && ` · torch ${system.hardware.torch_version}`}
            </p>
            {system.hardware.gpus.map((g) => (
              <p key={g.name} className="tabular-nums">{g.name} — {(g.vram_mb / 1024).toFixed(1)} GB {g.cuda && "· CUDA"}</p>
            ))}
            {system.hardware.warnings.map((w) => <p key={w} className="text-accent leading-relaxed">{w}</p>)}
          </div>
        )}
      </section>

      <section className="card p-5">
        <h3 className="eyebrow mb-3">External tools</h3>
        <div className="space-y-2">
          {system?.tools.map((t) => (
            <div key={t.name} className="flex items-center gap-2 text-[11px]">
              {t.found ? <CheckCircle2 size={14} className="text-txt" /> : <XCircle size={14} className="text-signal" />}
              <span className="w-16 uppercase tracking-wider2 text-sub">{t.name}</span>
              <span className="truncate text-[10px] text-dim">{t.found ? `${t.version ?? ""} — ${t.path}` : "not found"}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="card p-5 space-y-4">
        <h3 className="eyebrow">Preferences</h3>
        {FIELDS.map((f) => (
          <div key={f.key}>
            {f.type === "bool" ? (
              <div className="flex items-center justify-between">
                <span className="label">{f.label}</span>
                <Switch on={Boolean(values[f.key])} onChange={(v) => { setValues((s) => ({ ...s, [f.key]: v })); setDirty(true); }} />
              </div>
            ) : (
              <>
                <label className="label mb-1.5">{f.label}</label>
                <input className="input" type={f.type} value={(values[f.key] as string | number | null) ?? ""}
                  onChange={(e) => { setValues((s) => ({ ...s, [f.key]: f.type === "number" ? Number(e.target.value) : e.target.value })); setDirty(true); }} />
                {f.hint && <p className="mt-1 text-[10px] text-dim">{f.hint}</p>}
              </>
            )}
          </div>
        ))}
        <div className="flex justify-end gap-3 items-center">
          {saved && <span className="text-[10px] uppercase tracking-wider2 text-txt">Saved</span>}
          <button className="btn-primary" disabled={!dirty} onClick={save}>Save settings</button>
        </div>
      </section>
    </div>
  );
}
