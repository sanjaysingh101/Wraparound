import { useEffect, useRef, useState } from "react";
import * as GaussianSplats3D from "@mkkellogg/gaussian-splats-3d";
import * as THREE from "three";
import { Box, Camera, Crosshair, Grid3x3, Maximize2, Minus, Move3d, Orbit, Play, Square, Trash2, Video } from "lucide-react";
import { api, projectFileUrl } from "../lib/api";
import type { ProjectMeta } from "../lib/types";
import { useApp } from "../state/store";
import { AxisGizmo } from "./AxisGizmo";
import { CameraPath, FlyControls, suspendBuiltinControls, type Slot } from "../lib/viewerNav";
import { Readout, SectionLabel, Slider, Switch } from "./ui";

const BG_SWATCHES = ["#09090a", "#000000", "#ffffff", "#1a1d24", "#2b2e33"];

export function SplatViewer({ project }: { project: ProjectMeta }) {
  const refreshProjects = useApp((s) => s.refreshProjects);
  const setError = useApp((s) => s.setError);
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<GaussianSplats3D.Viewer | null>(null);
  const gridRef = useRef<THREE.GridHelper | null>(null);
  const boundsRef = useRef<THREE.Box3Helper | null>(null);
  const flyRef = useRef<FlyControls | null>(null);
  const pathRef = useRef<CameraPath | null>(null);
  const releaseRef = useRef<(() => void) | null>(null);
  const modeRef = useRef<"orbit" | "fly">("orbit");
  const playingRef = useRef(false);

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

  // navigation + fly-around
  const [navMode, setNavMode] = useState<"orbit" | "fly">("orbit");
  const [flySpeed, setFlySpeed] = useState(3);
  const [playing, setPlaying] = useState(false);
  const [slots, setSlots] = useState<Record<Slot, boolean>>({ start: false, middle: false, end: false });
  const [duration, setDuration] = useState(8);
  const [loop, setLoop] = useState(false);

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
        const mesh = viewer.getSplatMesh();
        setStats((s) => ({ ...s, splats: mesh?.getSplatCount() ?? 0 }));
        // scale fly speed to the scene so movement feels consistent across models
        const canvas = containerRef.current?.querySelector("canvas");
        if (canvas) {
          const fly = new FlyControls(viewer.camera, canvas);
          if (mesh) {
            const diag = new THREE.Box3().setFromObject(mesh).getSize(new THREE.Vector3()).length();
            fly.speed = (diag || 15) * 0.25;
            setFlySpeed(Math.round(fly.speed * 10) / 10);
          }
          flyRef.current = fly;
        }
        const path = new CameraPath();
        pathRef.current = path;
        // Pre-load the most recent saved fly-around so it's ready to play or edit.
        const last = project.flyarounds?.[project.flyarounds.length - 1];
        if (last) {
          const set = path.loadKeyframes(last.keyframes);
          setSlots({ start: set.includes("start"), middle: set.includes("middle"), end: set.includes("end") });
          setDuration(last.duration);
          setLoop(last.loop);
        }
      })
      .catch(() => setState("error"));

    // fps sampling + per-frame nav updates
    let frames = 0;
    let last = performance.now();
    let prev = performance.now();
    let raf = 0;
    const tick = () => {
      const now = performance.now();
      const dt = Math.min((now - prev) / 1000, 0.1);
      prev = now;
      if (playingRef.current && pathRef.current) {
        if (pathRef.current.update(dt, viewer.camera) === "done") setPlaying(false);
      } else if (modeRef.current === "fly") {
        flyRef.current?.update(dt);
      }
      frames += 1;
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
      flyRef.current?.disable();
      releaseRef.current?.();
      flyRef.current = null;
      pathRef.current = null;
      releaseRef.current = null;
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

  // ---- navigation mode + playback take over the camera from OrbitControls
  useEffect(() => {
    flyRef.current && (flyRef.current.speed = flySpeed);
  }, [flySpeed]);

  useEffect(() => {
    modeRef.current = navMode;
    playingRef.current = playing;
    const viewer = viewerRef.current;
    if (!viewer || state !== "ready") return;
    const takeover = navMode === "fly" || playing;
    if (takeover && !releaseRef.current) {
      releaseRef.current = suspendBuiltinControls(viewer);
    } else if (!takeover && releaseRef.current) {
      releaseRef.current();
      releaseRef.current = null;
    }
    if (navMode === "fly" && !playing) flyRef.current?.enable();
    else flyRef.current?.disable();
  }, [navMode, playing, state]);

  const setKeyframe = (slot: Slot) => {
    const viewer = viewerRef.current;
    if (!viewer || !pathRef.current) return;
    pathRef.current.setSlot(slot, viewer.camera);
    setSlots((s) => ({ ...s, [slot]: true }));
  };
  const playPath = async () => {
    const path = pathRef.current;
    if (!path) return;
    path.duration = duration;
    path.loop = loop;
    if (navMode === "fly") setNavMode("orbit");
    const keyframes = path.exportSlots();
    if (!path.play()) return;
    setPlaying(true);
    // Auto-save the fly-around that was just played, skipping an identical replay
    // of the most recently saved one so the list doesn't fill with duplicates.
    const round = (kf: { position: number[]; quaternion: number[] }[]) =>
      JSON.stringify(kf.map((k) => [k.position.map((n) => +n.toFixed(4)), k.quaternion.map((n) => +n.toFixed(4))]));
    const last = project.flyarounds?.[project.flyarounds.length - 1];
    if (keyframes.length >= 2 && (!last || round(last.keyframes) !== round(keyframes))) {
      try {
        await api.addFlyaround(project.id, {
          name: `Fly-around ${(project.flyarounds?.length ?? 0) + 1}`,
          keyframes,
          duration,
          loop,
        });
        await refreshProjects();
      } catch (e) {
        setError(String(e));
      }
    }
  };
  const stopPath = () => {
    pathRef.current?.stop();
    setPlaying(false);
  };
  const playSaved = (fa: ProjectMeta["flyarounds"][number]) => {
    const path = pathRef.current;
    if (!path) return;
    if (navMode === "fly") setNavMode("orbit");
    setDuration(fa.duration);
    setLoop(fa.loop);
    if (path.playSaved(fa.keyframes, fa.duration, fa.loop)) setPlaying(true);
  };
  const deleteFlyaround = async (id: string) => {
    try {
      await api.deleteFlyaround(project.id, id);
      await refreshProjects();
    } catch (e) {
      setError(String(e));
    }
  };

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

          {/* controls legend — mode aware */}
          <div className="absolute left-1/2 -translate-x-1/2 bottom-3 flex items-center gap-4 panel bg-panel/85 backdrop-blur px-4 py-1.5 text-[10px] uppercase tracking-wider2 text-dim">
            {playing ? (
              <span className="text-accent">playing fly-around…</span>
            ) : navMode === "fly" ? (
              <>
                <span><span className="text-sub">wasd</span> move</span>
                <span><span className="text-sub">q/e</span> down/up</span>
                <span><span className="text-sub">click</span> look</span>
                <span><span className="text-sub">shift</span> fast</span>
              </>
            ) : (
              <>
                <span><span className="text-sub">drag</span> orbit</span>
                <span><span className="text-sub">right-drag</span> pan</span>
                <span><span className="text-sub">scroll</span> zoom</span>
              </>
            )}
          </div>

          {/* fly-mode look hint */}
          {navMode === "fly" && !playing && (
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 pointer-events-none">
              <div className="h-3 w-3 border border-accent/70 rounded-full" />
            </div>
          )}

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

            {/* navigation */}
            <div className="pt-2 border-t border-white/10 space-y-3">
              <SectionLabel>Navigation</SectionLabel>
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  className={`flex items-center justify-center gap-1.5 h-8 rounded-te border text-[10px] uppercase tracking-wider2 transition-colors ${navMode === "orbit" ? "border-accent/50 text-accent bg-accent/10" : "border-white/10 text-sub hover:text-txt"}`}
                  onClick={() => setNavMode("orbit")}
                >
                  <Orbit size={13} /> Orbit
                </button>
                <button
                  className={`flex items-center justify-center gap-1.5 h-8 rounded-te border text-[10px] uppercase tracking-wider2 transition-colors ${navMode === "fly" ? "border-accent/50 text-accent bg-accent/10" : "border-white/10 text-sub hover:text-txt"}`}
                  onClick={() => setNavMode("fly")}
                >
                  <Move3d size={13} /> Fly
                </button>
              </div>
              {navMode === "fly" && (
                <div className="space-y-1.5">
                  <Readout label="fly speed" value={flySpeed.toFixed(1)} />
                  <Slider value={flySpeed} min={0.5} max={Math.max(20, flySpeed)} step={0.5} onChange={setFlySpeed} />
                </div>
              )}
            </div>

            {/* fly-around path */}
            <div className="pt-2 border-t border-white/10 space-y-3">
              <SectionLabel right={<Video size={13} className="text-dim" />}>Fly-around</SectionLabel>
              <p className="text-[10px] text-dim leading-relaxed">
                Aim the camera, then capture keyframes. Play interpolates a smooth path.
              </p>
              <div className="grid grid-cols-3 gap-1.5">
                {(["start", "middle", "end"] as Slot[]).map((s) => (
                  <button key={s} onClick={() => setKeyframe(s)}
                    className={`h-8 rounded-te border text-[10px] uppercase tracking-wider2 transition-colors ${slots[s] ? "border-accent/50 text-accent bg-accent/10" : "border-white/10 text-sub hover:text-txt"}`}>
                    {slots[s] ? "✓ " : "+ "}{s}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-3">
                <span className="label flex-1">duration</span>
                <input className="field w-16 text-center" type="number" min={1} max={60} value={duration}
                  onChange={(e) => setDuration(Math.max(1, Number(e.target.value) || 8))} />
                <span className="text-[10px] text-dim">s</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="label">loop</span>
                <Switch on={loop} onChange={setLoop} />
              </div>
              {playing ? (
                <button className="w-full h-9 flex items-center justify-center gap-2 rounded-te border border-signal/40 text-signal text-[11px] uppercase tracking-wider2 hover:bg-signal/10" onClick={stopPath}>
                  <Square size={13} /> Stop
                </button>
              ) : (
                <button
                  className="w-full h-9 flex items-center justify-center gap-2 rounded-te border border-accent/40 text-accent text-[11px] uppercase tracking-wider2 hover:bg-accent/10 disabled:opacity-30 disabled:pointer-events-none"
                  disabled={Object.values(slots).filter(Boolean).length < 2}
                  onClick={playPath}
                >
                  <Play size={13} /> Play &amp; save
                </button>
              )}
              {Object.values(slots).filter(Boolean).length >= 2 && (
                <p className="text-[9px] text-dim leading-relaxed">Playing saves this fly-around automatically.</p>
              )}

              {/* saved fly-arounds */}
              {(project.flyarounds?.length ?? 0) > 0 && (
                <div className="space-y-1 pt-1">
                  <p className="eyebrow px-1">Saved</p>
                  {project.flyarounds.map((fa) => (
                    <div key={fa.id} className="group flex items-center gap-2 h-8 px-2 rounded-te border border-white/10 hover:border-white/20">
                      <button
                        className="flex-1 flex items-center gap-2 min-w-0 text-left text-[10px] uppercase tracking-wider2 text-sub hover:text-txt disabled:opacity-40"
                        onClick={() => playSaved(fa)}
                        disabled={playing}
                        title="Play"
                      >
                        <Play size={11} className="shrink-0" />
                        <span className="truncate">{fa.name}</span>
                      </button>
                      <span className="text-[9px] text-dim tabular-nums shrink-0">
                        {fa.keyframes.length}kf·{fa.duration}s{fa.loop ? "·↻" : ""}
                      </span>
                      <button className="text-dim hover:text-signal shrink-0 opacity-0 group-hover:opacity-100" onClick={() => deleteFlyaround(fa.id)} title="Delete">
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
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
