import { useEffect } from "react";
import { jobSocket } from "./api";
import { useApp } from "../state/store";
import type { JobState } from "./types";

/** Subscribe to live pipeline progress for a project; auto-reconnects. */
export function useJobSocket(projectId: string | null) {
  const applyJobUpdate = useApp((s) => s.applyJobUpdate);
  const refreshProjects = useApp((s) => s.refreshProjects);

  useEffect(() => {
    if (!projectId) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: number | undefined;

    const connect = () => {
      ws = jobSocket(projectId);
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data) as { type: string; job?: JobState };
        if (msg.job) applyJobUpdate(msg.job);
        if (msg.type === "completed" || msg.type === "failed" || msg.type === "cancelled") {
          void refreshProjects();
        }
      };
      ws.onclose = () => {
        if (!closed) retry = window.setTimeout(connect, 2000);
      };
    };
    connect();

    return () => {
      closed = true;
      window.clearTimeout(retry);
      ws?.close();
    };
  }, [projectId, applyJobUpdate, refreshProjects]);
}
