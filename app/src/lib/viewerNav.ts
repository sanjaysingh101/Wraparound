import * as THREE from "three";

/**
 * Camera navigation for the splat viewer.
 *
 * The gaussian-splats-3d viewer drives its camera every frame with built-in
 * OrbitControls (which force `camera.lookAt(target)`), so to take manual control we
 * must neutralize that update loop, not merely set `enabled = false`.
 */
export function suspendBuiltinControls(viewer: {
  camera: THREE.PerspectiveCamera;
  controls?: { enabled: boolean; target: THREE.Vector3; update(): void };
}): () => void {
  const c = viewer.controls;
  if (!c) return () => {};
  const origUpdate = c.update.bind(c);
  const origEnabled = c.enabled;
  c.enabled = false;
  c.update = () => {}; // stop OrbitControls from overwriting our camera each frame
  return () => {
    c.update = origUpdate;
    c.enabled = origEnabled;
    // Re-anchor the orbit target in front of the camera so returning to orbit
    // doesn't snap the view.
    try {
      const cam = viewer.camera;
      const fwd = new THREE.Vector3();
      cam.getWorldDirection(fwd);
      const dist = c.target.distanceTo(cam.position) || 3;
      c.target.copy(cam.position).add(fwd.multiplyScalar(dist));
      origUpdate();
    } catch {
      /* ignore */
    }
  };
}

/** First-person fly controls: WASD move, Q/E down/up, mouse-look via pointer lock. */
export class FlyControls {
  speed = 3;
  private sensitivity = 0.0025;
  private keys = new Set<string>();
  private active = false;
  private pitch = 0;

  constructor(private camera: THREE.PerspectiveCamera, private canvas: HTMLElement) {}

  enable() {
    if (this.active) return;
    this.active = true;
    window.addEventListener("keydown", this.onKeyDown);
    window.addEventListener("keyup", this.onKeyUp);
    this.canvas.addEventListener("click", this.requestLock);
    document.addEventListener("pointerlockchange", this.onLockChange);
    document.addEventListener("mousemove", this.onMouseMove);
    this.canvas.style.cursor = "crosshair";
  }

  disable() {
    if (!this.active) return;
    this.active = false;
    this.keys.clear();
    window.removeEventListener("keydown", this.onKeyDown);
    window.removeEventListener("keyup", this.onKeyUp);
    this.canvas.removeEventListener("click", this.requestLock);
    document.removeEventListener("pointerlockchange", this.onLockChange);
    document.removeEventListener("mousemove", this.onMouseMove);
    if (document.pointerLockElement === this.canvas) document.exitPointerLock();
    this.canvas.style.cursor = "";
  }

  get locked() {
    return document.pointerLockElement === this.canvas;
  }

  private requestLock = () => this.canvas.requestPointerLock?.();
  private onLockChange = () => {};

  private isTyping() {
    const el = document.activeElement;
    return el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement;
  }

  private onKeyDown = (e: KeyboardEvent) => {
    if (this.isTyping()) return;
    const k = e.key.toLowerCase();
    if ("wasdqe".includes(k) || k === "shift") {
      this.keys.add(k);
      e.preventDefault();
    }
  };
  private onKeyUp = (e: KeyboardEvent) => this.keys.delete(e.key.toLowerCase());

  private onMouseMove = (e: MouseEvent) => {
    if (!this.locked) return;
    // yaw around the viewer's up axis; pitch around the camera's local right, clamped
    this.camera.rotateOnWorldAxis(this.camera.up, -e.movementX * this.sensitivity);
    const maxPitch = Math.PI / 2 - 0.05;
    const dp = -e.movementY * this.sensitivity;
    const next = THREE.MathUtils.clamp(this.pitch + dp, -maxPitch, maxPitch);
    this.camera.rotateX(next - this.pitch);
    this.pitch = next;
  };

  /** Call each frame with delta-time in seconds. */
  update(dt: number) {
    if (!this.active || this.keys.size === 0) return;
    const move = new THREE.Vector3();
    const fwd = new THREE.Vector3();
    this.camera.getWorldDirection(fwd);
    const right = new THREE.Vector3().crossVectors(fwd, this.camera.up).normalize();
    if (this.keys.has("w")) move.add(fwd);
    if (this.keys.has("s")) move.sub(fwd);
    if (this.keys.has("d")) move.add(right);
    if (this.keys.has("a")) move.sub(right);
    if (this.keys.has("e")) move.sub(this.camera.up); // up on screen (camera.up is -Y)
    if (this.keys.has("q")) move.add(this.camera.up);
    if (move.lengthSq() === 0) return;
    const boost = this.keys.has("shift") ? 3 : 1;
    move.normalize().multiplyScalar(this.speed * boost * dt);
    this.camera.position.add(move);
  }
}

export type Slot = "start" | "middle" | "end";
const SLOT_ORDER: Slot[] = ["start", "middle", "end"];

interface Keyframe {
  position: THREE.Vector3;
  quaternion: THREE.Quaternion;
}

function smoothstep(t: number) {
  return t * t * (3 - 2 * t);
}

/** Keyframed fly-around: capture start/middle/end camera poses, play a smooth path. */
export class CameraPath {
  duration = 8; // seconds
  loop = false;
  private slots: Partial<Record<Slot, Keyframe>> = {};
  private frames: Keyframe[] = [];
  private curve?: THREE.CatmullRomCurve3;
  private t = 0;
  playing = false;

  setSlot(slot: Slot, camera: THREE.PerspectiveCamera) {
    this.slots[slot] = {
      position: camera.position.clone(),
      quaternion: camera.quaternion.clone(),
    };
  }
  clearSlot(slot: Slot) {
    delete this.slots[slot];
  }
  hasSlot(slot: Slot) {
    return !!this.slots[slot];
  }
  get count() {
    return SLOT_ORDER.filter((s) => this.slots[s]).length;
  }

  play() {
    this.frames = SLOT_ORDER.filter((s) => this.slots[s]).map((s) => this.slots[s]!);
    if (this.frames.length < 2) return false;
    const pts = this.frames.map((f) => f.position);
    this.curve = new THREE.CatmullRomCurve3(pts, this.loop, "catmullrom", 0.5);
    this.t = 0;
    this.playing = true;
    return true;
  }
  stop() {
    this.playing = false;
  }

  /** Advance the animation; returns "done" when it finishes (non-looping). */
  update(dt: number, camera: THREE.PerspectiveCamera): "done" | null {
    if (!this.playing || !this.curve || this.frames.length < 2) return null;
    this.t += dt / Math.max(this.duration, 0.1);
    let done = false;
    if (this.t >= 1) {
      if (this.loop) this.t %= 1;
      else {
        this.t = 1;
        done = true;
      }
    }
    const te = smoothstep(THREE.MathUtils.clamp(this.t, 0, 1));
    camera.position.copy(this.curve.getPoint(te));

    // orientation: slerp between the two bracketing keyframes
    const n = this.frames.length - 1;
    const seg = Math.min(Math.floor(te * n), n - 1);
    const localT = smoothstep(te * n - seg);
    camera.quaternion.copy(this.frames[seg].quaternion).slerp(this.frames[seg + 1].quaternion, localT);

    if (done) this.playing = false;
    return done ? "done" : null;
  }
}
