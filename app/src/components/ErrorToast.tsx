import { X } from "lucide-react";
import { useApp } from "../state/store";

export function ErrorToast() {
  const error = useApp((s) => s.error);
  const setError = useApp((s) => s.setError);
  if (!error) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 max-w-md panel border-signal/40 bg-panel/95 p-4 shadow-2xl">
      <div className="flex items-start gap-3">
        <span className="eyebrow text-signal shrink-0 mt-0.5">Error</span>
        <p className="text-[12px] text-txt whitespace-pre-wrap flex-1 leading-relaxed">{error}</p>
        <button className="text-dim hover:text-txt shrink-0" onClick={() => setError(null)}>
          <X size={15} />
        </button>
      </div>
    </div>
  );
}
