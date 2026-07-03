import { Film } from "lucide-react";
import { projectFileUrl } from "../lib/api";
import type { ProjectMeta } from "../lib/types";
import { Readout } from "./ui";

export function SourcePanel({ project }: { project: ProjectMeta }) {
  const v = project.validation;
  const info = v?.video;

  if (!project.video_file) {
    return (
      <div className="flex h-full items-center justify-center text-center">
        <div className="space-y-2">
          <Film size={28} className="mx-auto text-dim" />
          <p className="text-[11px] uppercase tracking-wider2 text-sub">No source video</p>
          <p className="text-[11px] text-dim">Upload a video from the Pipeline tab.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl p-8 space-y-5">
      <div className="card overflow-hidden">
        <video
          key={project.id}
          className="w-full bg-black max-h-[62vh]"
          controls
          playsInline
          preload="metadata"
          poster={projectFileUrl(project.id, "preview/thumbnail.jpg")}
          src={projectFileUrl(project.id, "video.mp4")}
        />
      </div>

      {info && (
        <div className="grid grid-cols-2 gap-x-8 gap-y-2.5">
          <div className="space-y-2.5">
            <p className="eyebrow">Capture</p>
            <Readout label="resolution" value={`${info.width}×${info.height}`} />
            <Readout label="duration" value={`${info.duration_s.toFixed(1)}s`} />
            <Readout label="frame rate" value={`${info.fps} fps`} />
            <Readout label="bitrate" value={`${(info.bitrate_kbps / 1000).toFixed(1)} Mbps`} />
            <Readout label="codec" value={info.codec || "—"} />
          </div>
          <div className="space-y-2.5">
            <p className="eyebrow">Quality</p>
            <Readout label="sharpness" value={v.sharpness.toFixed(0)} />
            <Readout label="brightness" value={v.brightness.toFixed(0)} />
            <Readout label="shake" value={v.shakiness.toFixed(1)} />
            <Readout label="parallax" value={v.motion_coverage.toFixed(1)} />
          </div>
        </div>
      )}

      {v && v.issues.length > 0 && (
        <div className="card p-4 space-y-2">
          <p className="eyebrow">Notes</p>
          {v.issues.map((issue) => (
            <p key={issue.code} className="text-[11px] leading-relaxed">
              <span className={issue.severity === "reject" ? "text-signal" : "text-accent"}>
                {issue.severity === "reject" ? "✕ " : "! "}
              </span>
              <span className="text-sub">{issue.message}</span>
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
