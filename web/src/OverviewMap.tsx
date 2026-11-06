import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { FeatureCollection, Point } from "geojson";
import type { CaseSummary } from "./types";
import { createMap, setBasemap, UF_LABELS, esc, ESRI_ATTR } from "./mapbase";
import { priorityColor, scoreInt } from "./data";

type Props = {
  cases: CaseSummary[];
  hovered: string | null;
  onHover: (autex: string | null) => void;
};

function toFC(cases: CaseSummary[]): FeatureCollection<Point> {
  return {
    type: "FeatureCollection",
    features: cases
      .filter((c) => Array.isArray(c.centroide) && Number.isFinite(c.centroide[0]))
      .map((c) => ({
        type: "Feature",
        properties: {
          autex: c.autex,
          score: c.score,
          tipo: c.tipo,
          img: c.analise_imagem ? 1 : 0,
          mun: c.municipio,
          uf: c.uf,
          ind: c.flags.filter((f) => f.status === "indicio").length,
        },
        geometry: { type: "Point", coordinates: c.centroide },
      })),
  };
}

export function OverviewMap({ cases, hovered, onHover }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [basemap, setBm] = useState(false);
  const fitted = useRef(false);
  const hoverCb = useRef(onHover);
  hoverCb.current = onHover;

  useEffect(() => {
    if (!el.current) return;
    const m = createMap(el.current);
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    const markers = UF_LABELS.map(([uf, ll]) => {
      const div = document.createElement("div");
      div.className = "uf-label";
      div.textContent = uf;
      return new maplibregl.Marker({ element: div }).setLngLat(ll).addTo(m);
    });
    const tip = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: "tip" });
    m.on("load", () => {
      m.addSource("cases", { type: "geojson", data: toFC([]) });
      m.addSource("hl", { type: "geojson", data: toFC([]) });
      m.addLayer({
        id: "cases-img",
        type: "circle",
        source: "cases",
        filter: ["==", ["get", "img"], 1],
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 9, 10, 14],
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": "#c5f67c",
          "circle-stroke-width": 2,
        },
      });
      m.addLayer({
        id: "cases",
        type: "circle",
        source: "cases",
        layout: { "circle-sort-key": ["get", "score"] },
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            5,
            ["interpolate", ["linear"], ["get", "score"], 0, 3.5, 1, 6.5],
            10,
            ["interpolate", ["linear"], ["get", "score"], 0, 6, 1, 10],
          ],
          "circle-color": [
            "step",
            ["get", "score"],
            priorityColor.baixa,
            0.3,
            priorityColor.media,
            0.6,
            priorityColor.alta,
          ],
          "circle-stroke-color": "#0e261d",
          "circle-stroke-width": 1,
          "circle-opacity": 0.95,
        },
      });
      m.addLayer({
        id: "hl",
        type: "circle",
        source: "hl",
        paint: {
          "circle-radius": 15,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2.5,
        },
      });
      m.on("mousemove", "cases", (e) => {
        const f = e.features?.[0];
        if (!f) return;
        m.getCanvas().style.cursor = "pointer";
        const p = f.properties as Record<string, string | number>;
        tip
          .setLngLat((f.geometry as Point).coordinates as [number, number])
          .setHTML(
            `<b class="mono">${esc(p.autex)}</b><span>${esc(p.tipo)} · ${esc(p.mun)}/${esc(p.uf)}</span><span>Prioridade ${scoreInt(Number(p.score))}/100 · ${p.ind} indício(s)</span>`,
          )
          .addTo(m);
        hoverCb.current(String(p.autex));
      });
      m.on("mouseleave", "cases", () => {
        m.getCanvas().style.cursor = "";
        tip.remove();
        hoverCb.current(null);
      });
      m.on("click", "cases", (e) => {
        const a = e.features?.[0]?.properties?.autex;
        if (a) location.hash = `/caso/${encodeURIComponent(String(a))}`;
      });
      setReady(true);
    });
    return () => {
      markers.forEach((mk) => mk.remove());
      m.remove();
      map.current = null;
      fitted.current = false;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const fc = toFC(cases);
    (m.getSource("cases") as maplibregl.GeoJSONSource).setData(fc);
    if (!fitted.current && fc.features.length) {
      const b = new maplibregl.LngLatBounds();
      fc.features.forEach((f) => b.extend(f.geometry.coordinates as [number, number]));
      m.fitBounds(b, { padding: { top: 70, bottom: 90, left: 60, right: 60 }, maxZoom: 9, duration: 0 });
      fitted.current = true;
    }
  }, [cases, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const c = hovered ? cases.find((x) => x.autex === hovered) : undefined;
    (m.getSource("hl") as maplibregl.GeoJSONSource).setData(toFC(c ? [c] : []));
  }, [hovered, cases, ready]);

  useEffect(() => {
    if (map.current && ready) setBasemap(map.current, basemap);
  }, [basemap, ready]);

  return (
    <div className="overview-map">
      <div ref={el} className="map-fill" />
      <div className="map-legend overview-legend">
        <div className="legend-title">Prioridade de fiscalização</div>
        <ul>
          <li>
            <i className="dot" style={{ background: priorityColor.alta }} /> Alta · score ≥ 60
          </li>
          <li>
            <i className="dot" style={{ background: priorityColor.media }} /> Média · 30 a 59
          </li>
          <li>
            <i className="dot" style={{ background: priorityColor.baixa }} /> Baixa · abaixo de 30
          </li>
          <li>
            <i className="ring" /> Imagem de satélite analisada
          </li>
        </ul>
        <label className="toggle">
          <input type="checkbox" checked={basemap} onChange={(e) => setBm(e.target.checked)} />
          Imagem de fundo (Esri, requer internet)
        </label>
      </div>
      {basemap && <div className="attribution">{ESRI_ATTR}</div>}
    </div>
  );
}
