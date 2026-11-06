import type { CaseSummary, MetricsCalibracao } from "./types";
import { number } from "./data";
export function VolumeChart({ data: d }: { data: CaseSummary }) {
  const rows: [string, number | null][] = [
    ["Autorizado", d.volume_autorizado_m3],
    ["Declarado explorado", d.volume_declarado_explorado_m3],
    ["Estimado pela imagem", d.volume_estimado_m3.p50],
  ];
  const max = Math.max(
    1,
    ...rows.map((r) => r[1] ?? 0),
    d.volume_estimado_m3.p90 ?? 0,
  );
  const x = (n: number) => 145 + (n / max) * 200;
  return (
    <svg
      role="img"
      aria-label="Volumes em metros cúbicos; estimativa com intervalo p10 a p90"
      viewBox="0 0 430 155"
    >
      {rows.map(([label, value], i) => (
        <g key={label}>
          <text x="0" y={25 + i * 43}>
            {label}
          </text>
          <rect
            x="145"
            y={12 + i * 43}
            width={value === null ? 0 : (value / max) * 200}
            height="20"
            fill={i === 2 ? "#608557" : i === 1 ? "#173a2c" : "#bbc8b8"}
          />
          <text x="425" y={26 + i * 43} textAnchor="end">
            {value === null ? "N/A" : number(value)}
          </text>
          {i === 2 &&
            d.volume_estimado_m3.p10 !== null &&
            d.volume_estimado_m3.p90 !== null && (
              <>
                <line
                  x1={x(d.volume_estimado_m3.p10)}
                  x2={x(d.volume_estimado_m3.p90)}
                  y1="108"
                  y2="108"
                  stroke="#173a2c"
                  strokeWidth="2"
                />
                {[d.volume_estimado_m3.p10, d.volume_estimado_m3.p90].map(
                  (v) => (
                    <line
                      key={v}
                      x1={x(v)}
                      x2={x(v)}
                      y1="101"
                      y2="115"
                      stroke="#173a2c"
                      strokeWidth="2"
                    />
                  ),
                )}
              </>
            )}
        </g>
      ))}
      <text x="145" y="149">
        0
      </text>
      <text x="345" y="149" textAnchor="end">
        {number(max)} m³
      </text>
    </svg>
  );
}
export function CalibrationChart({ data: d }: { data: MetricsCalibracao }) {
  if (!d.curva.length) return <p>Curva não avaliada.</p>;
  const max = Math.max(1, ...d.curva.map((p) => p.p90));
  const x = (v: number) => 55 + v * 510,
    y = (v: number) => 240 - (v / max) * 205;
  const line = (key: "p10" | "p50" | "p90") =>
    d.curva.map((p) => `${x(p.disturbio_frac)},${y(p[key])}`).join(" ");
  return (
    <svg
      className="calibration-chart"
      viewBox="0 0 610 290"
      role="img"
      aria-label="Curva de calibração: faixa p10 a p90 e mediana p50"
    >
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <g key={f}>
          <line
            x1="55"
            x2="565"
            y1={y(max * f)}
            y2={y(max * f)}
            stroke="#e1e5db"
          />
          <text x="45" y={y(max * f) + 4} textAnchor="end">
            {number(max * f)}
          </text>
          <text x={x(f)} y="261" textAnchor="middle">
            {number(f)}
          </text>
        </g>
      ))}
      <polygon
        points={`${line("p90")} ${[...d.curva]
          .reverse()
          .map((p) => `${x(p.disturbio_frac)},${y(p.p10)}`)
          .join(" ")}`}
        fill="#d9e7cf"
      />
      <polyline
        points={line("p50")}
        fill="none"
        stroke="#173a2c"
        strokeWidth="3"
      />
      <text x="55" y="18">
        Volume estimado (m³/ha)
      </text>
      <text x="310" y="285" textAnchor="middle">
        Fração de distúrbio
      </text>
      <text x="390" y="18">
        p50 — faixa p10–p90
      </text>
    </svg>
  );
}
