import type { CaseSummary, MetricsCalibracao } from "./types";
import { fmt, fmtVol } from "./data";

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const m = v / p;
  const n = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((s) => m <= s + 1e-9) ?? 10;
  return n * p;
}

/** Barras horizontais: autorizado | declarado explorado | estimado pela imagem (p50 com faixa p10–p90). */
export function VolumeChart({ data: d }: { data: CaseSummary }) {
  const est = d.volume_estimado_m3;
  const rows = [
    { key: "aut", label: "Autorizado", sub: "Sinaflor", value: d.volume_autorizado_m3, color: "#c9d3c2" },
    { key: "dec", label: "Declarado explorado", sub: "IF100 / DOF", value: d.volume_declarado_explorado_m3, color: "#173a2c" },
    { key: "est", label: "Estimado pela imagem", sub: "mediana p50", value: est.p50, color: "#5f8f4e" },
  ];
  const max = niceMax(Math.max(1, ...rows.map((r) => r.value ?? 0), est.p90 ?? 0));
  const W = 428,
    plot = W - 2,
    rowH = 52,
    top = 0;
  const x = (v: number) => 1 + (v / max) * plot;
  const H = top + rows.length * rowH + 20;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  const hasBand = est.p10 != null && est.p90 != null;
  return (
    <figure className="vchart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Volumes em metros cúbicos: autorizado, declarado e estimado pela imagem com intervalo p10 a p90">
        {ticks.map((t, i) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top + 22} y2={top + rows.length * rowH} stroke="#e4e8dc" />
            <text x={x(t)} y={H - 4} textAnchor={i === 0 ? "start" : i === ticks.length - 1 ? "end" : "middle"} className="axis">
              {fmt(t, 0)}
              {i === ticks.length - 1 ? " m³" : ""}
            </text>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = top + i * rowH;
          const v = r.value;
          return (
            <g key={r.key}>
              <text x={0} y={y + 15} className="lbl">
                {r.label}
                <tspan className="sub" dx={8}>
                  {r.sub}
                </tspan>
              </text>
              <text x={W} y={y + 15} textAnchor="end" className="val">
                {v == null ? "não avaliado" : `${fmtVol(v)} m³`}
              </text>
              {v == null ? (
                <rect x={1} y={y + 23} width={plot} height={18} fill="url(#na)" stroke="#d4dacb" />
              ) : (
                <rect x={1} y={y + 23} width={Math.max(2, x(v) - 1)} height={18} fill={r.color} rx={2} />
              )}
              {r.key === "est" && hasBand && (
                <g className="band">
                  <line x1={x(est.p10!)} x2={x(est.p90!)} y1={y + 32} y2={y + 32} stroke="#0e261d" strokeWidth={2} />
                  <line x1={x(est.p10!)} x2={x(est.p10!)} y1={y + 24} y2={y + 40} stroke="#0e261d" strokeWidth={2} />
                  <line x1={x(est.p90!)} x2={x(est.p90!)} y1={y + 24} y2={y + 40} stroke="#0e261d" strokeWidth={2} />
                </g>
              )}
            </g>
          );
        })}
        <defs>
          <pattern id="na" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="#f6f7f1" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="#dfe4d6" strokeWidth="2" />
          </pattern>
        </defs>
      </svg>
      <figcaption>
        {hasBand ? (
          <>
            Traço preto: faixa provável do volume compatível com a imagem, de <b>{fmtVol(est.p10)}</b> a <b>{fmtVol(est.p90)} m³</b> (p10–p90).
          </>
        ) : (
          <>Estimativa pela imagem não avaliada para esta autorização.</>
        )}
      </figcaption>
    </figure>
  );
}

/** Curva de calibração: fração de distúrbio → volume (m³/ha), banda p10–p90 e mediana. */
export function CalibrationChart({ data: d }: { data: MetricsCalibracao }) {
  const pts = [...d.curva].sort((a, b) => a.disturbio_frac - b.disturbio_frac);
  if (!pts.length) return <p className="muted">Curva de calibração não disponível.</p>;
  const W = 640,
    H = 300,
    L = 56,
    R = 16,
    T = 18,
    B = 46;
  const xMax = Math.max(1e-6, ...pts.map((p) => p.disturbio_frac));
  const yMax = niceMax(Math.max(1, ...pts.map((p) => p.p90)));
  const x = (v: number) => L + (v / xMax) * (W - L - R);
  const y = (v: number) => T + (1 - v / yMax) * (H - T - B);
  const path = (k: "p10" | "p50" | "p90") => pts.map((p, i) => `${i ? "L" : "M"}${x(p.disturbio_frac).toFixed(1)},${y(p[k]).toFixed(1)}`).join(" ");
  const band =
    pts.map((p, i) => `${i ? "L" : "M"}${x(p.disturbio_frac).toFixed(1)},${y(p.p90).toFixed(1)}`).join(" ") +
    " " +
    [...pts]
      .reverse()
      .map((p) => `L${x(p.disturbio_frac).toFixed(1)},${y(p.p10).toFixed(1)}`)
      .join(" ") +
    " Z";
  const nT = Number.isInteger(yMax / 4) ? 4 : 5;
  const yt = Array.from({ length: nT + 1 }, (_, i) => (i / nT) * yMax);
  const xt = [0, 0.25, 0.5, 0.75, 1].map((f) => f * xMax);
  const last = pts[pts.length - 1];
  return (
    <svg className="cchart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Curva de calibração do volume: mediana e faixa p10 a p90 por fração de distúrbio">
      {yt.map((t) => (
        <g key={`y${t}`}>
          <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="#e4e8dc" />
          <text x={L - 8} y={y(t) + 4} textAnchor="end" className="axis">
            {fmt(t, 0)}
          </text>
        </g>
      ))}
      {xt.map((t) => (
        <text key={`x${t}`} x={x(t)} y={H - B + 18} textAnchor="middle" className="axis">
          {Math.round(t * 100)}%
        </text>
      ))}
      <path d={band} fill="#cfe3bf" opacity={0.85} />
      <path d={path("p10")} fill="none" stroke="#8fb57a" strokeWidth={1} />
      <path d={path("p90")} fill="none" stroke="#8fb57a" strokeWidth={1} />
      <path d={path("p50")} fill="none" stroke="#173a2c" strokeWidth={2.5} />
      {(() => {
        const mid = pts[Math.floor(pts.length * 0.72)] ?? last;
        const xm = x(mid.disturbio_frac);
        const gap = y(mid.p10) - y(mid.p50);
        return (
          <>
            <text x={xm} y={y(mid.p90) - 8} textAnchor="middle" className="ann">
              p90
            </text>
            <text x={xm} y={y(mid.p50) - 8} textAnchor="middle" className="ann strong">
              mediana p50
            </text>
            {gap > 22 && (
              <text x={xm} y={y(mid.p10) + 16} textAnchor="middle" className="ann">
                p10
              </text>
            )}
          </>
        );
      })()}      <text x={L} y={T - 6} className="axis-title">
        m³ por hectare
      </text>
      <text x={(L + W - R) / 2} y={H - 8} textAnchor="middle" className="axis-title">
        Fração da célula com distúrbio detectado
      </text>
    </svg>
  );
}

/** Termômetro simples para cobertura empírica vs nominal. */
export function CoverageBar({ value, nominal }: { value: number | null; nominal: number }) {
  if (value == null) return <p className="muted">Cobertura não avaliada.</p>;
  const W = 420,
    H = 54,
    x = (v: number) => 4 + v * (W - 8);
  return (
    <svg className="covbar" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Cobertura empírica ${Math.round(value * 100)}%, nominal ${Math.round(nominal * 100)}%`}>
      <rect x={4} y={14} width={W - 8} height={12} fill="#eef1e8" rx={2} />
      <rect x={4} y={14} width={x(value) - 4} height={12} fill="#5f8f4e" rx={2} />
      <line x1={x(nominal)} x2={x(nominal)} y1={6} y2={34} stroke="#0e261d" strokeWidth={2} />
      <text x={x(nominal)} y={48} textAnchor="middle" className="axis">
        nominal {Math.round(nominal * 100)}%
      </text>
      <text x={4} y={48} className="axis">
        0%
      </text>
      <text x={W - 4} y={48} textAnchor="end" className="axis">
        100%
      </text>
    </svg>
  );
}
