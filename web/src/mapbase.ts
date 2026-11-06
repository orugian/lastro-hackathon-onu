import * as maplibregl from "maplibre-gl";
import type { StyleSpecification } from "@maplibre/maplibre-gl-style-spec";
import type { FeatureCollection } from "geojson";
import ufs from "./uf.json";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

// O Vite pré-empacota o maplibre e quebra a resolução relativa do worker; apontamos o arquivo explicitamente.
maplibregl.setWorkerUrl(workerUrl);

export const ESRI_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
export const ESRI_ATTR = "Imagem de fundo: Esri, Maxar, Earthstar Geographics";

export const UF_LABELS: [string, [number, number]][] = [
  ["AM", [-64.6, -4.6]],
  ["RO", [-62.6, -10.9]],
  ["AC", [-70.2, -9.2]],
  ["MT", [-56.5, -12.6]],
  ["PA", [-53.2, -5.6]],
  ["RR", [-61.4, 2.0]],
];

/** Estilo offline: fundo sólido + contornos de UF embutidos + basemap opcional (desligado por padrão). */
export function baseStyle(bg = "#10261c", basemap = false): StyleSpecification {
  return {
    version: 8,
    sources: {
      ufs: { type: "geojson", data: ufs as FeatureCollection },
      esri: { type: "raster", tiles: [ESRI_TILES], tileSize: 256, maxzoom: 18 },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": bg } },
      { id: "uf-fill", type: "fill", source: "ufs", paint: { "fill-color": "#173a2c", "fill-opacity": 0.55 } },
      {
        id: "esri",
        type: "raster",
        source: "esri",
        layout: { visibility: basemap ? "visible" : "none" },
        paint: { "raster-fade-duration": 150, "raster-saturation": -0.15 },
      },
      {
        id: "uf-line",
        type: "line",
        source: "ufs",
        paint: { "line-color": "#6d8b78", "line-width": 1, "line-opacity": 0.7 },
      },
    ],
  };
}

export function createMap(container: HTMLElement, opts: { bg?: string; basemap?: boolean; interactive?: boolean } = {}) {
  return new maplibregl.Map({
    container,
    style: baseStyle(opts.bg, opts.basemap),
    center: [-63.5, -8.5],
    zoom: 5.5,
    attributionControl: false,
    interactive: opts.interactive ?? true,
    dragRotate: false,
    pitchWithRotate: false,
    touchPitch: false,
    fadeDuration: 0,
  });
}

export function setBasemap(m: maplibregl.Map, on: boolean) {
  if (m.getLayer("esri")) m.setLayoutProperty("esri", "visibility", on ? "visible" : "none");
}

export function boundsOf(fc: FeatureCollection) {
  const b = new maplibregl.LngLatBounds();
  const walk = (c: unknown): void => {
    if (!Array.isArray(c)) return;
    if (typeof c[0] === "number" && typeof c[1] === "number") b.extend([c[0], c[1]]);
    else c.forEach(walk);
  };
  for (const f of fc.features) if (f.geometry && "coordinates" in f.geometry) walk(f.geometry.coordinates);
  return b;
}

export const imageCoords = (b: [number, number, number, number]): [[number, number], [number, number], [number, number], [number, number]] => [
  [b[0], b[3]],
  [b[2], b[3]],
  [b[2], b[1]],
  [b[0], b[1]],
];

export function esc(v: unknown) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}
