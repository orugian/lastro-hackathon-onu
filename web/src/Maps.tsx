import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { FeatureCollection, Geometry } from "geojson";
import type { CaseSummary, Dossier, Evidencia } from "./types";
import { getData, imageUrl, number } from "./data";
import "maplibre-gl/dist/maplibre-gl.css";
const colors: Record<string, string> = {
  upa: "#c5f67c",
  buffer: "#dddccc",
  celulas: "#b62ab3",
  arvores: "#dbebbd",
  mudanca: "#ef4444",
  deter: "#d97706",
  prodes: "#cb88df",
  dndvi: "#64c4bd",
};
export const layerNames: Record<string, string> = {
  upa: "UPA autorizada",
  buffer: "Faixa de entorno",
  celulas: "Células de análise",
  arvores: "Árvores declaradas",
  mudanca: "Mudança detectada",
  deter: "Alertas DETER",
  prodes: "PRODES",
  dndvi: "Variação de NDVI",
};
const style: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#203b31" },
    },
  ],
};
function create(el: HTMLDivElement) {
  return new maplibregl.Map({
    container: el,
    style,
    center: [-63.3, -8.1],
    zoom: 6,
    attributionControl: false,
  });
}
export function OverviewMap({ cases }: { cases: CaseSummary[] }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!el.current) return;
    const m = create(el.current);
    m.addControl(new maplibregl.NavigationControl(), "top-right");
    m.on("load", () => {
      m.addSource("cases", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: cases.map((c) => ({
            type: "Feature",
            properties: { autex: c.autex, score: c.score },
            geometry: { type: "Point", coordinates: c.centroide },
          })),
        },
      });
      m.addLayer({
        id: "cases",
        type: "circle",
        source: "cases",
        paint: {
          "circle-radius": 12,
          "circle-color": [
            "step",
            ["get", "score"],
            "#c5f67c",
            40,
            "#e3a04a",
            70,
            "#e97474",
          ],
          "circle-stroke-width": 3,
          "circle-stroke-color": "#fff",
        },
      });
      m.on("click", "cases", (e) => {
        location.hash = `/caso/${e.features?.[0].properties.autex}`;
      });
      m.on("mouseenter", "cases", () => {
        m.getCanvas().style.cursor = "pointer";
      });
      m.on("mouseleave", "cases", () => {
        m.getCanvas().style.cursor = "";
      });
      if (cases.length) {
        const b = new maplibregl.LngLatBounds();
        cases.forEach((c) => b.extend(c.centroide));
        m.fitBounds(b, { padding: 100, maxZoom: 10, duration: 0 });
      }
    });
    return () => m.remove();
  }, [cases]);
  return (
    <div className="overview-map">
      <div ref={el} className="map-fill" />
      <div className="map-caption">
        <b>AMACRO</b>
        <span>Sul do Amazonas · Rondônia</span>
      </div>
      <div className="map-note">
        Prioridade de fiscalização · clique em um ponto
        <br />
        <span>Baixa &lt; 40 · Média 40–69 · Alta ≥ 70</span>
      </div>
    </div>
  );
}
function boundsOf(features: FeatureCollection) {
  const b = new maplibregl.LngLatBounds();
  function walk(c: unknown) {
    if (Array.isArray(c)) {
      if (typeof c[0] === "number" && typeof c[1] === "number")
        b.extend([c[0], c[1]]);
      else c.forEach(walk);
    }
  }
  features.features.forEach((f) => {
    if (f.geometry && "coordinates" in f.geometry) walk(f.geometry.coordinates);
  });
  return b;
}
export function ComparisonMap({
  dossier: d,
  focus,
}: {
  dossier: Dossier;
  focus?: Evidencia;
}) {
  const before = useRef<HTMLDivElement>(null),
    after = useRef<HTMLDivElement>(null),
    maps = useRef<maplibregl.Map[]>([]);
  const [sensor, setSensor] = useState(
    d.imagens.find((i) => i.par)?.sensor ?? "Sentinel-2",
  );
  const [swipe, setSwipe] = useState(50);
  const [enabled, setEnabled] = useState<string[]>(["upa", "mudanca"]);
  const [errors, setErrors] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(0);
  const geo = useRef<Record<string, FeatureCollection>>({});
  const pair = d.imagens.filter((i) => i.sensor === sensor && i.par);
  const sensors = [
    ...new Set(d.imagens.filter((i) => i.par).map((i) => i.sensor)),
  ];
  useEffect(() => {
    if (!before.current || !after.current) return;
    setErrors([]);
    setLoaded(0);
    const ms = [create(before.current), create(after.current)];
    maps.current = ms;
    let syncing = false;
    ms.forEach((m, index) => {
      m.on("move", () => {
        if (syncing) return;
        syncing = true;
        ms[1 - index].jumpTo({
          center: m.getCenter(),
          zoom: m.getZoom(),
          bearing: m.getBearing(),
          pitch: m.getPitch(),
        });
        syncing = false;
      });
      m.on("load", async () => {
        m.fitBounds(
          [
            [d.bbox[0], d.bbox[1]],
            [d.bbox[2], d.bbox[3]],
          ],
          { padding: 35, duration: 0 },
        );
        const img = pair.find((i) => i.par === (index === 0 ? "pre" : "pos"));
        if (img) {
          const [x, y, X, Y] = img.bounds;
          m.addSource("satellite", {
            type: "image",
            url: imageUrl(d.autex, img.png),
            coordinates: [
              [x, Y],
              [X, Y],
              [X, y],
              [x, y],
            ],
          });
          m.addLayer({
            id: "satellite",
            type: "raster",
            source: "satellite",
            paint: { "raster-fade-duration": 0 },
          });
        }
        const hatch = new Uint8Array(8 * 8 * 4);
        for (let y = 0; y < 8; y++)
          for (let x = 0; x < 8; x++) {
            const i = (y * 8 + x) * 4;
            hatch[i] = hatch[i + 1] = hatch[i + 2] = 170;
            hatch[i + 3] = (x + y) % 6 < 2 ? 220 : 35;
          }
        m.addImage("hatch", { width: 8, height: 8, data: hatch });
        for (const name of d.camadas) {
          try {
            const fc = await getData<FeatureCollection>(
              `/cases/${d.autex}/layers/${name}`,
            );
            if (!maps.current.includes(m)) return;
            geo.current[name] = fc;
            m.addSource(name, {
              type: "geojson",
              data: fc,
              cluster: name === "arvores" && fc.features.length > 5000,
              clusterRadius: 35,
            });
            const visibility = enabled.includes(name) ? "visible" : "none";
            if (name === "arvores") {
              m.addLayer({
                id: name,
                type: "circle",
                source: name,
                layout: { visibility },
                paint: {
                  "circle-radius": ["case", ["has", "point_count"], 9, 3],
                  "circle-color": [
                    "case",
                    ["==", ["get", "dentro_upa"], false],
                    "#ef4444",
                    "#dbebbd",
                  ],
                },
              });
            } else if (name === "celulas") {
              m.addLayer({
                id: name,
                type: "fill",
                source: name,
                layout: { visibility },
                paint: {
                  "fill-color": [
                    "match",
                    ["get", "classe"],
                    "sem_lastro",
                    "#b62ab3",
                    "nao_declarado",
                    "#ef4444",
                    "consistente",
                    "#9cbc8c",
                    "nao_observavel",
                    "#999999",
                    "rgba(0,0,0,0)",
                  ],
                  "fill-opacity": 0.4,
                },
              });
              m.addLayer({
                id: "hatching",
                type: "fill",
                source: name,
                filter: ["==", ["get", "classe"], "nao_observavel"],
                layout: { visibility },
                paint: { "fill-pattern": "hatch" },
              });
            } else {
              m.addLayer({
                id: name,
                type: "line",
                source: name,
                layout: { visibility },
                paint: {
                  "line-color": colors[name] ?? "#ccc",
                  "line-width": name === "upa" ? 2.5 : 1.5,
                  ...(name === "upa" ? { "line-dasharray": [4, 3] } : {}),
                },
              });
            }
            m.on("click", name, (e) => {
              const p = e.features?.[0].properties;
              if (!p) return;
              const box = document.createElement("div");
              box.textContent =
                name === "celulas"
                  ? `Célula ${p.id} · ${p.classe} | Declarado: ${number(p.vol_declarado)} m³ | p10 / p50 / p90: ${number(p.vol_p10)} / ${number(p.vol_p50)} / ${number(p.vol_p90)} m³`
                  : name === "arvores"
                    ? `${p.especie ?? "Espécie não informada"} · ${number(p.vol_explorado)} m³ · ${p.data_exploracao ?? "Data não informada"} · ${p.dentro_upa ? "Dentro da UPA" : "Fora da UPA"}`
                    : layerNames[name];
              new maplibregl.Popup()
                .setLngLat(e.lngLat)
                .setDOMContent(box)
                .addTo(m);
            });
          } catch {
            setErrors((old) => [
              ...new Set([...old, layerNames[name] ?? name]),
            ]);
          }
        }
        const ndvi = d.imagens.find(
          (i) => i.id === "dndvi" || i.png.includes("dndvi"),
        );
        if (ndvi) {
          const [x, y, X, Y] = ndvi.bounds;
          m.addSource("dndvi", {
            type: "image",
            url: imageUrl(d.autex, ndvi.png),
            coordinates: [
              [x, Y],
              [X, Y],
              [X, y],
              [x, y],
            ],
          });
          m.addLayer({
            id: "dndvi",
            type: "raster",
            source: "dndvi",
            layout: { visibility: "none" },
            paint: { "raster-opacity": 0.65 },
          });
        }
        setLoaded((x) => x + 1);
      });
    });
    ms[1].addControl(new maplibregl.NavigationControl(), "top-right");
    return () => {
      maps.current = [];
      ms.forEach((m) => m.remove());
    };
  }, [d, sensor]);
  useEffect(() => {
    maps.current.forEach((m) => {
      [...d.camadas, "dndvi"].forEach((n) => {
        if (m.getLayer(n))
          m.setLayoutProperty(
            n,
            "visibility",
            enabled.includes(n) ? "visible" : "none",
          );
      });
      if (m.getLayer("hatching"))
        m.setLayoutProperty(
          "hatching",
          "visibility",
          enabled.includes("celulas") ? "visible" : "none",
        );
    });
  }, [enabled, loaded, d]);
  useEffect(() => {
    if (!focus?.camada || loaded < 2) return;
    const name = focus.camada;
    setEnabled((v) => [...new Set([...v, name])]);
    const fc = geo.current[name];
    if (!fc) return;
    const selected: FeatureCollection<Geometry> = {
      type: "FeatureCollection",
      features: fc.features.filter(
        (f) =>
          !focus.filtro ||
          Object.entries(focus.filtro).every(
            ([k, v]) => f.properties?.[k] === v,
          ),
      ),
    };
    maps.current.forEach((m) => {
      if (m.getLayer("highlight")) m.removeLayer("highlight");
      if (m.getSource("highlight")) m.removeSource("highlight");
      m.addSource("highlight", { type: "geojson", data: selected });
      m.addLayer(
        name === "arvores"
          ? {
              id: "highlight",
              source: "highlight",
              type: "circle",
              paint: {
                "circle-color": "#fff",
                "circle-radius": 7,
                "circle-stroke-width": 3,
                "circle-stroke-color": "#991b1b",
              },
            }
          : {
              id: "highlight",
              source: "highlight",
              type: "line",
              paint: { "line-color": "#fff", "line-width": 4 },
            },
      );
      const b = boundsOf(selected);
      if (!b.isEmpty()) m.fitBounds(b, { padding: 70, maxZoom: 17 });
    });
  }, [focus, loaded]);
  return (
    <div className="comparison">
      <div className="map-tools">
        <b>Comparação temporal</b>
        <label>
          Sensor{" "}
          <select
            value={sensor}
            onChange={(e) => setSensor(e.target.value as typeof sensor)}
          >
            {sensors.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="swipe-map">
        <div ref={before} className="map-fill" />
        <div
          ref={after}
          className="map-fill"
          style={{ clipPath: `inset(0 0 0 ${swipe}%)` }}
        />
        <span className="image-label pre">
          Antes · {pair.find((i) => i.par === "pre")?.data ?? "Não avaliado"}
        </span>
        <span className="image-label post">
          Depois · {pair.find((i) => i.par === "pos")?.data ?? "Não avaliado"}
        </span>
        <div className="swipe-line" style={{ left: `${swipe}%` }}>
          <span>↔</span>
        </div>
        {pair.length < 2 && (
          <div className="map-note">
            Par de imagens incompleto · comparação não avaliada
          </div>
        )}
      </div>
      <label className="swipe-control">
        Antes{" "}
        <input
          aria-label="Comparar antes e depois"
          type="range"
          min="0"
          max="100"
          value={swipe}
          onChange={(e) => setSwipe(+e.target.value)}
        />{" "}
        Depois
      </label>
      <div className="legend">
        {[
          ...d.camadas,
          ...(d.imagens.some((i) => i.png.includes("dndvi")) ? ["dndvi"] : []),
        ].map((n) => (
          <label key={n}>
            <input
              type="checkbox"
              checked={enabled.includes(n)}
              onChange={() =>
                setEnabled((v) =>
                  v.includes(n) ? v.filter((x) => x !== n) : [...v, n],
                )
              }
            />
            <i style={{ background: colors[n] }} />
            {layerNames[n] ?? n}
          </label>
        ))}
      </div>
      <p className="caption">
        Células: roxo = sem lastro observável · vermelho = não declarado · verde
        = consistente · hachura = não observável.
      </p>
      {errors.length > 0 && (
        <p role="alert">
          Camadas indisponíveis: {errors.join(", ")}. Recarregue para tentar
          novamente.
        </p>
      )}
    </div>
  );
}
