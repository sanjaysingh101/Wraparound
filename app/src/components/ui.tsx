import type { ReactNode } from "react";

/** Teenage-Engineering dot-matrix block. `lit` marks indices that glow accent. */
export function DotMatrix({
  cols = 10,
  rows = 6,
  lit = [],
  className = "",
  gap = 3,
  size = 2,
}: {
  cols?: number;
  rows?: number;
  lit?: number[];
  className?: string;
  gap?: number;
  size?: number;
}) {
  const litSet = new Set(lit);
  return (
    <div
      className={className}
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${cols}, ${size}px)`,
        gap: `${gap}px`,
      }}
    >
      {Array.from({ length: cols * rows }).map((_, i) => (
        <span
          key={i}
          style={{
            width: size,
            height: size,
            borderRadius: 999,
            background: litSet.has(i) ? "var(--te-accent, #ff5c26)" : "rgba(255,255,255,0.14)",
          }}
        />
      ))}
    </div>
  );
}

export function Switch({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return <button className="switch" data-on={on} onClick={() => onChange(!on)} aria-pressed={on} />;
}

export function Slider({
  value,
  min,
  max,
  step = 0.01,
  onChange,
}: {
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <input
      type="range"
      className="slider"
      min={min}
      max={max}
      step={step}
      value={value}
      onChange={(e) => onChange(parseFloat(e.target.value))}
    />
  );
}

const DOT_COLORS: Record<string, string> = {
  running: "#ff5c26",
  completed: "#e9eaec",
  failed: "#ff453a",
  idle: "#4c4f55",
};

export function StatusDot({ status }: { status: keyof typeof DOT_COLORS }) {
  return (
    <span
      className={`dot ${status === "running" ? "animate-pulse" : ""}`}
      style={{ background: DOT_COLORS[status] ?? DOT_COLORS.idle }}
    />
  );
}

export function SectionLabel({ children, right }: { children: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-center justify-between px-1 mb-2">
      <span className="eyebrow">{children}</span>
      {right}
    </div>
  );
}

/** A labelled row with a value readout on the right (instrument display). */
export function Readout({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="label">{label}</span>
      <span className="text-[12px] text-txt tabular-nums">{value}</span>
    </div>
  );
}
