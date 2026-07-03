import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { PipelineConfig, ProjectMeta } from "../lib/types";
import { useApp } from "../state/store";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card p-5 space-y-4">
      <h3 className="eyebrow">{title}</h3>
      {children}
    </section>
  );
}

export function ConfigPanel({ project }: { project: ProjectMeta }) {
  const { system, refreshProjects, setError } = useApp();
  const [cfg, setCfg] = useState<PipelineConfig>(project.config);
  const [dirty, setDirty] = useState(false);
  const running = project.job?.status === "running";

  useEffect(() => {
    setCfg(project.config);
    setDirty(false);
  }, [project.id, project.config]);

  const patch = (updater: (c: PipelineConfig) => PipelineConfig) => {
    setCfg((c) => updater(structuredClone(c)));
    setDirty(true);
  };
  const save = async () => {
    try {
      await api.updateConfig(project.id, cfg);
      await refreshProjects();
      setDirty(false);
    } catch (e) {
      setError(String(e));
    }
  };
  const num = (v: string, fallback: number) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5 p-8">
      <Section title="Frame extraction">
        <div className="grid grid-cols-3 gap-4">
          <Field label="Min frames"><input className="input" type="number" value={cfg.extraction.target_min_frames}
            onChange={(e) => patch((c) => { c.extraction.target_min_frames = num(e.target.value, 150); return c; })} /></Field>
          <Field label="Max frames"><input className="input" type="number" value={cfg.extraction.target_max_frames}
            onChange={(e) => patch((c) => { c.extraction.target_max_frames = num(e.target.value, 500); return c; })} /></Field>
          <Field label="JPEG quality"><input className="input" type="number" value={cfg.extraction.quality}
            onChange={(e) => patch((c) => { c.extraction.quality = num(e.target.value, 95); return c; })} /></Field>
        </div>
      </Section>

      <Section title="Camera poses">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Backend">
            <select className="input" value={cfg.poses.backend} onChange={(e) => patch((c) => { c.poses.backend = e.target.value; return c; })}>
              {(system?.backends.poses ?? ["colmap"]).map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </Field>
          <Field label="Matcher">
            <select className="input" value={cfg.poses.matcher} onChange={(e) => patch((c) => { c.poses.matcher = e.target.value; return c; })}>
              <option value="sequential">Sequential (video)</option>
              <option value="exhaustive">Exhaustive (robust)</option>
            </select>
          </Field>
        </div>
      </Section>

      <Section title="Training">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Backend">
            <select className="input" value={cfg.training.backend} onChange={(e) => patch((c) => { c.training.backend = e.target.value; return c; })}>
              {(system?.backends.train ?? ["splatfacto", "gsplat"]).map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </Field>
          <Field label="Iterations"><input className="input" type="number" step={1000} value={cfg.training.iterations}
            onChange={(e) => patch((c) => { c.training.iterations = num(e.target.value, 30000); return c; })} /></Field>
          <Field label="Learning rate"><input className="input" type="number" step="0.00001" value={cfg.training.learning_rate}
            onChange={(e) => patch((c) => { c.training.learning_rate = num(e.target.value, 0.00016); return c; })} /></Field>
          <Field label="SH degree">
            <select className="input" value={cfg.training.sh_degree} onChange={(e) => patch((c) => { c.training.sh_degree = num(e.target.value, 3); return c; })}>
              {[0, 1, 2, 3].map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </Field>
          <Field label="Background">
            <select className="input" value={cfg.training.background_color} onChange={(e) => patch((c) => { c.training.background_color = e.target.value; return c; })}>
              <option value="black">Black</option>
              <option value="white">White</option>
              <option value="random">Random</option>
            </select>
          </Field>
          <Field label="Opacity reset"><input className="input" type="number" step={500} value={cfg.training.opacity_reset_interval}
            onChange={(e) => patch((c) => { c.training.opacity_reset_interval = num(e.target.value, 3000); return c; })} /></Field>
          <Field label="Densify from"><input className="input" type="number" step={100} value={cfg.training.densify_from_iter}
            onChange={(e) => patch((c) => { c.training.densify_from_iter = num(e.target.value, 500); return c; })} /></Field>
          <Field label="Densify until"><input className="input" type="number" step={500} value={cfg.training.densify_until_iter}
            onChange={(e) => patch((c) => { c.training.densify_until_iter = num(e.target.value, 15000); return c; })} /></Field>
        </div>
      </Section>

      <div className="flex items-center justify-end gap-3">
        {running && <span className="text-[10px] uppercase tracking-wider2 text-accent">Applies to next run</span>}
        <button className="btn-primary" disabled={!dirty} onClick={save}>Save config</button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="label mb-1.5">{label}</label>
      {children}
    </div>
  );
}
