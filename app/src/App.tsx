import { useEffect } from "react";
import { Sidebar } from "./components/Sidebar";
import { HomeView } from "./components/HomeView";
import { ProjectView } from "./components/ProjectView";
import { SettingsView } from "./components/SettingsView";
import { ErrorToast } from "./components/ErrorToast";
import { useApp } from "./state/store";

export default function App() {
  const view = useApp((s) => s.view);
  const backendUp = useApp((s) => s.backendUp);
  const refreshProjects = useApp((s) => s.refreshProjects);
  const refreshSystem = useApp((s) => s.refreshSystem);

  useEffect(() => {
    void refreshProjects();
    void refreshSystem();
    // The backend sidecar may still be booting when the shell opens — poll until up.
    const t = window.setInterval(() => {
      if (!useApp.getState().backendUp) {
        void refreshProjects();
        void refreshSystem();
      }
    }, 1500);
    return () => window.clearInterval(t);
  }, [refreshProjects, refreshSystem]);

  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex-1 min-w-0 overflow-y-auto">
        {!backendUp ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center space-y-2">
              <div className="animate-pulse text-[13px] uppercase tracking-widest2 text-sub">
                Starting local engine…
              </div>
              <p className="text-[10px] uppercase tracking-wider2 text-dim">
                Runs entirely on this machine
              </p>
            </div>
          </div>
        ) : view.kind === "home" ? (
          <HomeView />
        ) : view.kind === "project" ? (
          <ProjectView projectId={view.id} />
        ) : (
          <SettingsView />
        )}
      </main>
      <ErrorToast />
    </div>
  );
}
