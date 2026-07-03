import { useEffect, useRef, useState } from "react";

type Quat = [number, number, number, number]; // x, y, z, w

/** Rotate vector v by the inverse of quaternion q (world → camera space). */
function applyInverseQuat(q: Quat, v: [number, number, number]): [number, number, number] {
  const [qx, qy, qz, qw] = q;
  // inverse of a unit quaternion is its conjugate
  const ix = -qx,
    iy = -qy,
    iz = -qz,
    iw = qw;
  // t = 2 * cross(i, v)
  const tx = 2 * (iy * v[2] - iz * v[1]);
  const ty = 2 * (iz * v[0] - ix * v[2]);
  const tz = 2 * (ix * v[1] - iy * v[0]);
  return [
    v[0] + iw * tx + (iy * tz - iz * ty),
    v[1] + iw * ty + (iz * tx - ix * tz),
    v[2] + iw * tz + (ix * ty - iy * tx),
  ];
}

const AXES: { dir: [number, number, number]; label: string; color: string }[] = [
  { dir: [1, 0, 0], label: "X", color: "#ff5c26" },
  { dir: [0, 1, 0], label: "Y", color: "#d8d9db" },
  { dir: [0, 0, 1], label: "Z", color: "#4a7bd6" },
];

export function AxisGizmo({ getQuat, size = 96 }: { getQuat: () => Quat | null; size?: number }) {
  const [quat, setQuat] = useState<Quat>([0, 0, 0, 1]);
  const raf = useRef(0);

  useEffect(() => {
    const tick = () => {
      const q = getQuat();
      if (q) setQuat(q);
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [getQuat]);

  const c = size / 2;
  const r = size * 0.34;

  // project each axis (+ and −) into 2D camera space, sort by depth
  const marks = AXES.flatMap(({ dir, label, color }) =>
    [1, -1].map((s) => {
      const v = applyInverseQuat(quat, [dir[0] * s, dir[1] * s, dir[2] * s]);
      return {
        x: c + v[0] * r,
        y: c - v[1] * r, // screen y is down
        z: v[2],
        label: s === 1 ? label : "",
        color,
        positive: s === 1,
      };
    }),
  ).sort((a, b) => a.z - b.z);

  return (
    <svg width={size} height={size} className="overflow-visible">
      <circle cx={c} cy={c} r={r} fill="none" stroke="rgba(255,255,255,0.10)" strokeWidth="1" />
      <circle cx={c} cy={c} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="1"
        transform={`scale(1 0.34)`} style={{ transformOrigin: `${c}px ${c}px` }} />
      {marks.map((m, i) => (
        <g key={i} opacity={0.35 + 0.65 * ((m.z + 1) / 2)}>
          {m.positive && <line x1={c} y1={c} x2={m.x} y2={m.y} stroke={m.color} strokeWidth="1.5" />}
          <circle cx={m.x} cy={m.y} r={m.positive ? 3.2 : 2}
            fill={m.positive ? m.color : "#09090a"}
            stroke={m.color} strokeWidth="1" />
          {m.label && (
            <text x={m.x} y={m.y} dx={5} dy={3} fontSize="9" fill={m.color}
              fontFamily="ui-monospace, monospace">{m.label}</text>
          )}
        </g>
      ))}
    </svg>
  );
}
