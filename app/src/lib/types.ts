// Mirrors backend/splatstudio/models.py

export type StageName =
  | "preparing"
  | "extracting_frames"
  | "filtering_frames"
  | "estimating_poses"
  | "training"
  | "optimizing"
  | "generating_preview"
  | "completed";

export type StageStatus = "pending" | "running" | "completed" | "failed" | "skipped";

export interface StageState {
  name: StageName;
  status: StageStatus;
  progress: number;
  message: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  outputs: Record<string, unknown>;
}

export interface JobState {
  project_id: string;
  status: StageStatus;
  current_stage?: StageName | null;
  stages: StageState[];
  started_at?: string | null;
  finished_at?: string | null;
  elapsed_s: number;
  eta_s?: number | null;
  error?: string | null;
}

export interface VideoInfo {
  path: string;
  width: number;
  height: number;
  fps: number;
  duration_s: number;
  frame_count: number;
  bitrate_kbps: number;
  rotation: number;
  codec: string;
}

export interface ValidationIssue {
  code: string;
  severity: "reject" | "warn";
  message: string;
}

export interface ValidationReport {
  video: VideoInfo;
  issues: ValidationIssue[];
  sharpness: number;
  brightness: number;
  shakiness: number;
  motion_coverage: number;
}

export interface TrainingConfig {
  backend: string;
  iterations: number;
  learning_rate: number;
  sh_degree: number;
  background_color: string;
  densify_from_iter: number;
  densify_until_iter: number;
  densify_grad_threshold: number;
  opacity_reset_interval: number;
  extra: Record<string, unknown>;
}

export interface PipelineConfig {
  extraction: { target_min_frames: number; target_max_frames: number; quality: number };
  poses: { backend: string; matcher: string; extra: Record<string, unknown> };
  training: TrainingConfig;
}

export interface ExportRecord {
  file: string;
  format: string;
  bytes: number;
  created_at: string;
  gaussians?: number;
}

export interface CameraKeyframe {
  position: number[]; // [x, y, z]
  quaternion: number[]; // [x, y, z, w]
}

export interface Flyaround {
  id: string;
  name: string;
  keyframes: CameraKeyframe[];
  duration: number;
  loop: boolean;
  created_at: string;
}

export interface ProjectMeta {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  video_file?: string | null;
  validation?: ValidationReport | null;
  config: PipelineConfig;
  job?: JobState | null;
  exports: ExportRecord[];
  flyarounds: Flyaround[];
  stats: Record<string, unknown>;
}

export interface GPUInfo {
  name: string;
  vram_mb: number;
  cuda: boolean;
}

export interface HardwareInfo {
  platform: string;
  cpu_cores: number;
  ram_mb: number;
  gpus: GPUInfo[];
  cuda_available: boolean;
  mps_available: boolean;
  torch_version?: string | null;
  warnings: string[];
}

export interface ToolStatus {
  name: string;
  found: boolean;
  path?: string | null;
  version?: string | null;
}

export interface SystemStatus {
  hardware: HardwareInfo;
  tools: ToolStatus[];
  training_available: boolean;
  backends: { poses: string[]; train: string[]; export: string[] };
}

export interface ExportFormatInfo {
  format: string;
  available: boolean;
  reason: string;
}

export const STAGE_LABELS: Record<StageName, string> = {
  preparing: "Preparing",
  extracting_frames: "Extracting Frames",
  filtering_frames: "Filtering Frames",
  estimating_poses: "Running COLMAP",
  training: "Training Gaussians",
  optimizing: "Optimizing",
  generating_preview: "Generating Preview",
  completed: "Completed",
};
