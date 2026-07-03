import { useEffect, useRef, useState } from "react";
import * as GaussianSplats3D from "@mkkellogg/gaussian-splats-3d";
import * as THREE from "three";
import { Box, Camera, Crosshair, Grid3x3, Maximize2, Minus } from "lucide-react";
import { projectFileUrl } from "../lib/api";
import type { ProjectMeta } from "../lib/types";
import { AxisGizmo } from "./AxisGizmo";
import { Readout, SectionLabel, Slider, Switch } from "./ui";

const BG_SWATCHES = ["#09090a", "#000000", "#ffffff", "#1a1d24", "#2b2e33"];

export function SplatViewer({ project }: { project: ProjectMeta }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<GaussianSplats3D.Viewer | null>(null);
  const gridRef = useRef<THREE.GridHelper | null>(null);
  const boundsRef = useRef<THREE.Box3Helper | null>(null);

  const [state, setState] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const [stats, setStats] = useState({ splats: 0, fps: 0 });
  const [fpsHistory, setFpsHistory] = useState<number[]>([]);
  const [panelOpen, setPanelOpen] = useState(true);

  // viewer controls
  const [pointSize, setPointSize] = useState(1.0);
  const [opacity, setOpacity] = useState(0.85);
  const [shading, setShading] = useState<"pbr" | "points">("pbr");
  const [showGrid, setShowGrid] = useState(false);
  const [showBounds, setShowBounds] = useState(true);
  const [background, setBackground] = useState(BG_SWATCHES[0]);
  const [bgOpen, setBgOpen] = useState(false);

  const trained = project.job?.status === "completed" || project.stats["ply_bytes"] != null;

  // ---- viewer lifecycle
  useEffect(() => {
    if (!trained || !containerRef.current) {
      setState("empty");
      return;
    }
    setState("loading");
    const viewer = new GaussianSplats3D.Viewer({
      rootElement: containerRef.current,
      selfDrivenMode: true,
      useBuiltInControls: true,
      sharedMemoryForWorkers: false,
      dynamicScene: false,
      // COLMAP/OpenSplat world space renders upside down under the viewer default.
      cameraUp: [0, -1, 0],
    });
    viewerRef.current = viewer;

    viewer
      .addSplatScene(projectFileUrl(project.id, "splat/point_cloud.ply"), {
        showLoadingUI: false,
        progressiveLoad: true,
      })
      .then(() => {
        viewer.start();
        setState("ready");
        setStats((s) => ({ ...s, splats: viewer.getSplatMesh()?.getSplatCount() ?? 0 }));
      })
      .catch(() => setState("error"));

    // fps sampling + rolling history for the sparkline
    let frames = 0;
    let last = performance.now();
    let raf = 0;
    const tick = () => {
      frames += 1;
      const now = performance.now();
      if (now - last >= 500) {
        const fps = Math.round((frames * 1000) / (now - last));
        setStats((s) => ({ ...s, fps }));
        setFpsHistory((h) => [...h.slice(-39), fps]);
        frames = 0;
        last = now;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      viewerRef.current = null;
      gridRef.current = null;
      boundsRef.current = null;
      viewer.dispose().catch(() => {});
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, trained]);

  // ---- wire controls to the live viewer
  useEffect(() => {
    const v = viewerRef.current;
    if (v?.renderer) v.renderer.setClearColor(new THREE.Color(background), 1);
    if (containerRef.current) containerRef.current.style.background = background;
  }, [background, state]);

  useEffect(() => {
    try {
      viewerRef.current?.getSplatMesh()?.setSplatScale?.(pointSize);
    } catch { /* older build */ }
  }, [pointSize, state]);

  useEffect(() => {
    try {
      viewerRef.current?.getSplatMesh()?.setPointCloudModeEnabled?.(shading === "points");
    } catch { /* older build */ }
  }, [shading, state]);

  useEffect(() => {
    // best-effort global opacity via the splat mesh material
    try {
      const mat = (viewerRef.current?.getSplatMesh() as unknown as { material?: THREE.Material })?.material;
      if (mat) {
        mat.transparent = true;
        (mat as THREE.Material & { opacity: number }).opacity = opacity;
      }
    } catch { /* ignore */ }
  }, [opacity, state]);

  useEffect(() => {
    const v = viewerRef.current;
    const scene = v?.threeScene as THREE.Scene | undefined;
    if (!scene || state !== "ready") return;
    if (showGrid && !gridRef.current) {
      const g = new THREE.GridHelper(10, 20, 0x444444, 0x222222);
      g.rotation.x = Math.PI / 2; // align to COLMAP/OpenSplat ground (Y-down space)
      gridRef.current = g;
      scene.add(g);
    } else if (!showGrid && gridRef.current) {
      scene.remove(gridRef.current);
      gridRef.current = null;
    }
  }, [showGrid, state]);

  useEffect(() => {
    const v = viewerRef.current;
    const scene = v?.threeScene as THREE.Scene | undefined;
    if (!scene || state !== "ready") return;
    if (showBounds && !boundsRef.current) {
      const mesh = v?.getSplatMesh();
      const box = new THREE.Box3();
      if (mesh) box.setFromObject(mesh);
      const helper = new THREE.Box3Helper(box, new THREE.Color("#ff5c26"));
      boundsRef.current = helper;
      scene.add(helper);
    } else if (!showBounds && boundsRef.current) {
      scene.remove(boundsRef.current);
      boundsRef.current = null;
    }
  }, [showBounds, state]);

  // ---- toolbar actions
  const resetView = () => viewerRef.current?.getSplatMesh() && window.location.reload();
  const screenshot = () => {
    const canvas = containerRef.current?.querySelector("canvas");
    if (!canvas) return;
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = `${project.name.replace(/\s+/g, "_")}.png`;
    a.click();
  };
  const fullscreen = () => containerRef.current?.requestFullscreen().catch(() => {});
  const getQuat = (): [number, number, number, number] | null => {
    const q = viewerRef.current?.camera?.quaternion;
    return q ? [q.x, q.y, q.z, q.w] : null;
  };

  if (!trained) {
    return (
      <div className="flex h-full items-center justify-center text-center">
        <div className="space-y-1">
          <p className="text-[11px] uppercase tracking-wider2 text-sub">No trained splat</p>
          <p className="text-[11px] text-dim">Run the pipeline — the viewer opens when training completes.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* viewport */}
      <div className="relative flex-1 min-w-0 p-4">
        <div className="relative h-full w-full rounded-te overflow-hidden border border-white/10">
          <div ref={containerRef} className="absolute inset-0" />

          {state === "loading" && (
            <div className="absolute inset-0 grid place-items-center text-[11px] uppercase tracking-wider2 text-sub animate-pulse">
              Loading splat…
            </div>
          )}
          {state === "error" && (
            <div className="absolute inset-0 grid place-items-center text-[11px] uppercase tracking-wider2 text-signal">
              Failed to load model
            </div>
          )}

          {/* toolbar */}
          <div className="absolute left-3 top-3 flex items-center gap-0.5 panel bg-panel/85 backdrop-blur px-1 py-1">
            <ToolBtn title="Reset view" onClick={resetView}><Crosshair size={15} /></ToolBtn>
            <ToolBtn title="Grid" active={showGrid} onClick={() => setShowGrid((v) => !v)}><Grid3x3 size={15} /></ToolBtn>
            <ToolBtn title="Bounds" active={showBounds} onClick={() => setShowBounds((v) => !v)}><Box size={15} /></ToolBtn>
            <ToolBtn title="Screenshot" onClick={screenshot}><Camera size={15} /></ToolBtn>
            <ToolBtn title="Fullscreen" onClick={fullscreen}><Maximize2 size={15} /></ToolBtn>
          </div>

          {/* stats readout */}
          {state === "ready" && (
            <div className="absolute left-3 bottom-3 panel bg-panel/85 backdrop-blur px-3 py-2 min-w-[130px]">
              <div className="text-[18px] text-txt tabular-nums leading-none">
                {stats.splats.toLocaleString()}
              </div>
              <div className="eyebrow mt-0.5">splats</div>
              <div className="text-[13px] text-txt tabular-nums mt-2 leading-none">{stats.fps} fps</div>
              <div className="eyebrow">real-time</div>
              <Sparkline data={fpsHistory} />
            </div>
          )}

          {/* controls legend */}
          <div className="absolute left-1/2 -translate-x-1/2 bottom-3 flex items-center gap-4 panel bg-panel/85 backdrop-blur px-4 py-1.5 text-[10px] uppercase tracking-wider2 text-dim">
            <span><span className="text-sub">orbit</span></span>
            <span><span className="text-sub">right-drag</span> pan</span>
            <span><span className="text-sub">scroll</span> zoom</span>
          </div>

          {/* axis gizmo */}
          <div className="absolute right-3 bottom-3 panel bg-panel/70 backdrop-blur p-2 grid place-items-center">
            <AxisGizmo getQuat={getQuat} size={92} />
          </div>
        </div>
      </div>

      {/* right control panel */}
      {panelOpen ? (
        <div className="w-64 shrink-0 border-l border-white/10 bg-surface overflow-y-auto">
          <div className="flex items-center justify-between px-4 h-11 border-b border-white/10">
            <span className="eyebrow">Viewer</span>
            <button className="icon-btn h-6 w-6" onClick={() => setPanelOpen(false)}><Minus size={14} /></button>
          </div>

          <div className="p-4 space-y-5">
            <div className="space-y-1.5">
              <Readout label="point size" value={pointSize.toFixed(2)} />
              <Slider value={pointSize} min={0.2} max={2} step={0.05} onChange={setPointSize} />
            </div>
            <div className="space-y-1.5">
              <Readout label="splat opacity" value={opacity.toFixed(2)} />
              <Slider value={opacity} min={0.1} max={1} step={0.01} onChange={setOpacity} />
            </div>

            <div className="space-y-1.5">
              <span className="label">shading</span>
              <div className="relative">
                <select className="field" value={shading} onChange={(e) => setShading(e.target.value as "pbr" | "points")}>
                  <option value="pbr">PBR</option>
                  <option value="points">POINTS</option>
                </select>
                <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-dim text-[10px]">▼</span>
              </div>
            </div>

            <div className="space-y-2.5 pt-1">
              <ToggleRow label="show grid" on={showGrid} onChange={setShowGrid} />
              <ToggleRow label="show bounds" on={showBounds} onChange={setShowBounds} />
            </div>

            <div className="flex items-center justify-between">
              <span className="label">background</span>
              <div className="relative">
                <button className="flex items-center gap-1.5" onClick={() => setBgOpen((o) => !o)}>
                  <span className="h-4 w-4 rounded-full border border-white/20" style={{ background }} />
                  <span className="text-dim text-[10px]">▼</span>
                </button>
                {bgOpen && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setBgOpen(false)} />
                    <div className="absolute right-0 top-6 z-20 panel p-2 flex gap-1.5">
                      {BG_SWATCHES.map((c) => (
                        <button key={c} className={`h-5 w-5 rounded-full border ${background === c ? "border-accent" : "border-white/20"}`}
                          style={{ background: c }} onClick={() => { setBackground(c); setBgOpen(false); }} />
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="pt-2 border-t border-white/10">
              <SectionLabel>Model</SectionLabel>
              <div className="space-y-1.5">
                <Readout label="backend" value={String(project.stats["backend"] ?? "—")} />
                <Readout label="iterations" value={String(project.stats["iterations"] ?? "—")} />
                <Readout label="registered" value={String(project.stats["registered"] ?? "—")} />
              </div>
            </div>
          </div>
        </div>
      ) : (
        <button className="w-8 shrink-0 border-l border-white/10 bg-surface grid place-items-center text-dim hover:text-txt"
          onClick={() => setPanelOpen(true)} title="Show panel">
          <span className="[writing-mode:vertical-rl] text-[10px] uppercase tracking-wider2">Viewer</span>
        </button>
      )}
    </div>
  );
}

function ToolBtn({ children, onClick, title, active }: { children: React.ReactNode; onClick: () => void; title: string; active?: boolean }) {
  return (
    <button title={title} onClick={onClick}
      className={`grid place-items-center h-8 w-8 rounded-te transition-colors ${active ? "text-accent bg-accent/10" : "text-sub hover:text-txt hover:bg-white/5"}`}>
      {children}
    </button>
  );
}

function ToggleRow({ label, on, onChange }: { label: string; on: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between">
      <span className="label">{label}</span>
      <Switch on={on} onChange={onChange} />
    </div>
  );
}

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return <div className="h-5 mt-1" />;
  const max = Math.max(...data, 1);
  const w = 100, h = 20;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - (v / max) * h}`).join(" ");
  return (
    <svg width={w} height={h} className="mt-1.5 w-full" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke="#ff5c26" strokeWidth="1" opacity="0.7" />
    </svg>
  );
}
