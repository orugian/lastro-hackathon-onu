import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { Feature, FeatureCollection } from "geojson";
import type { LayerSpecification } from "@maplibre/maplibre-gl-style-spec";
import type { CelulaClasse, Dossier, Evidencia, Imagem } from "./types";
import { getData, imageUrl, fmt, fmtDate, fmtPeriod, pct } from "./data";
import { boundsOf, createMap, esc, imageCoords, setBasemap, ESRI_ATTR } from "./mapbase";
import { Icon } from "./ui";

export type Focus = { ev: Evidencia; nonce: number };

export const layerInfo: Record<string, { label: string; color: string; kind: "line" | "fill" | "dot" | "dash" }> = {
  upa: { label: "UPA / área autorizada", color: "#c5f67c", kind: "dash" },
  buffer: { label: "Entorno analisado (2 km)", color: "#e7e9d9", kind: "line" },
  celulas: { label: "Células de 1 ha", color: "#c026d3", kind: "fill" },
  arvores: { label: "Árvores declaradas (IF100)", color: "#f4f1d0", kind: "dot" },
  mudanca: { label: "Polígonos de distúrbio", color: "#ff4d4d", kind: "line" },
  deter: { label: "Alertas DETER", color: "#f59e0b", kind: "fill" },
  prodes: { label: "PRODES (corte raso)", color: "#facc15", kind: "line" },
};

export const cellClasses: { id: CelulaClasse; label: string; color: string }[] = [
  { id: "sem_lastro", label: "Declarado sem lastro observável", color: "#d946ef" },
  { id: "nao_declarado", label: "Distúrbio não declarado", color: "#ef4444" },
  { id: "consistente", label: "Consistente", color: "#86c98a" },
  { id: "nao_observavel", label: "Não observável (nuvem)", color: "#9ca3af" },
  { id: "sem_atividade", label: "Sem atividade", color: "transparent" },
];
const classLabel = Object.fromEntries(cellClasses.map((c) => [c.id, c.label])) as Record<string, string>;

const sensorShort: Record<string, string> = {
  "Sentinel-2": "Sentinel-2 · 10 m",
  "CBERS-4A WPM": "CBERS-4A · 2 m",
};

const ORDER = ["prodes", "deter", "celulas", "buffer", "upa", "mudanca", "arvores"];
const DISPLAY = ["upa", "buffer", "celulas", "arvores", "mudanca", "deter", "prodes"];

type Popup = { lngLat: [number, number]; html: string } | null;

function addVectorLayers(m: maplibregl.Map, name: string, fc: FeatureCollection, visible: boolean) {
  const vis = visible ? "visible" : "none";
  const cluster = name === "arvores" && fc.features.length > 5000;
  m.addSource(`v-${name}`, {
    type: "geojson",
    data: fc,
    ...(cluster
      ? {
          cluster: true,
          clusterRadius: 30,
          clusterMaxZoom: 15,
          clusterProperties: { fora: ["+", ["case", ["==", ["get", "dentro_upa"], false], 1, 0]] },
        }
      : {}),
  });
  const src = `v-${name}`;
  const ids: string[] = [];
  const add = (spec: LayerSpecification) => {
    const layout = "layout" in spec ? (spec.layout ?? {}) : {};
    m.addLayer({ ...spec, layout: { ...layout, visibility: vis } } as LayerSpecification);
    ids.push(spec.id);
  };
  switch (name) {
    case "upa":
      add({ id: "upa-glow", type: "line", source: src, paint: { "line-color": "#0e261d", "line-width": 5, "line-opacity": 0.55 } });
      add({ id: "upa", type: "line", source: src, paint: { "line-color": "#c5f67c", "line-width": 2.5, "line-dasharray": [3, 2] } });
      break;
    case "buffer":
      add({ id: "buffer", type: "line", source: src, paint: { "line-color": "#e7e9d9", "line-width": 1, "line-opacity": 0.75, "line-dasharray": [1, 2] } });
      break;
    case "celulas":
      add({
        id: "celulas",
        type: "fill",
        source: src,
        filter: ["!=", ["get", "classe"], "sem_atividade"],
        paint: {
          "fill-color": ["match", ["get", "classe"], ...cellClasses.flatMap((c) => [c.id, c.color === "transparent" ? "rgba(0,0,0,0)" : c.color]), "rgba(0,0,0,0)"] as unknown as string,
          "fill-opacity": ["match", ["get", "classe"], "consistente", 0.28, "nao_observavel", 0.35, 0.62] as unknown as number,
          "fill-outline-color": "rgba(14,38,29,0.35)",
        },
      });
      add({ id: "celulas-hatch", type: "fill", source: src, filter: ["==", ["get", "classe"], "nao_observavel"], paint: { "fill-pattern": "hatch" } });
      add({
        id: "celulas-edge",
        type: "line",
        source: src,
        filter: ["in", ["get", "classe"], ["literal", ["sem_lastro", "nao_declarado"]]],
        paint: { "line-color": ["match", ["get", "classe"], "sem_lastro", "#f5d0fe", "#fecaca"] as unknown as string, "line-width": 0.8 },
      });
      break;
    case "arvores":
      if (cluster)
        add({
          id: "arvores-cluster",
          type: "circle",
          source: src,
          filter: ["has", "point_count"],
          paint: {
            "circle-color": ["case", [">", ["get", "fora"], 0], "#ef4444", "#f4f1d0"] as unknown as string,
            "circle-radius": ["step", ["get", "point_count"], 8, 50, 12, 500, 17] as unknown as number,
            "circle-opacity": 0.85,
            "circle-stroke-color": "#0e261d",
            "circle-stroke-width": 1,
          },
        });
      add({
        id: "arvores",
        type: "circle",
        source: src,
        filter: cluster ? ["!", ["has", "point_count"]] : ["all"],
        paint: {
          "circle-radius": ["case", ["==", ["get", "dentro_upa"], false], 5.5, 2.4] as unknown as number,
          "circle-color": ["case", ["==", ["get", "dentro_upa"], false], "#ef4444", "#f4f1d0"] as unknown as string,
          "circle-stroke-color": ["case", ["==", ["get", "dentro_upa"], false], "#ffffff", "#0e261d"] as unknown as string,
          "circle-stroke-width": ["case", ["==", ["get", "dentro_upa"], false], 1.5, 0.6] as unknown as number,
        },
      });
      break;
    case "mudanca":
      add({ id: "mudanca-fill", type: "fill", source: src, paint: { "fill-color": "#ff4d4d", "fill-opacity": 0.18 } });
      add({ id: "mudanca", type: "line", source: src, paint: { "line-color": "#ff4d4d", "line-width": 2.2 } });
      break;
    case "deter":
      add({ id: "deter-fill", type: "fill", source: src, paint: { "fill-color": "#f59e0b", "fill-opacity": 0.22 } });
      add({ id: "deter", type: "line", source: src, paint: { "line-color": "#f59e0b", "line-width": 1.8 } });
      break;
    case "prodes":
      add({ id: "prodes-fill", type: "fill", source: src, paint: { "fill-color": "#facc15", "fill-opacity": 0.12 } });
      add({ id: "prodes", type: "line", source: src, paint: { "line-color": "#facc15", "line-width": 1.6, "line-dasharray": [2, 1.5] } });
      break;
    default:
      add({ id: name, type: "line", source: src, paint: { "line-color": "#ffffff", "line-width": 1.2 } });
  }
  return ids;
}

function popupHtml(layer: string, p: Record<string, unknown>): string {
  const n = (v: unknown) => (v == null || v === "" ? null : Number(v));
  const row = (k: string, v: string) => `<div><dt>${esc(k)}</dt><dd>${v}</dd></div>`;
  if (layer.startsWith("celulas")) {
    const cls = String(p.classe ?? "");
    return `<h4>Célula ${esc(p.id)}</h4><p class="pop-tag pop-${esc(cls)}">${esc(classLabel[cls] ?? cls)}</p><dl>${row(
      "Volume declarado",
      `${fmt(n(p.vol_declarado))} m³ · ${fmt(n(p.n_arvores), 0)} árv.`,
    )}${row("Compatível com a imagem", `${fmt(n(p.vol_p10))} – ${fmt(n(p.vol_p90))} m³`)}${row("Mediana (p50)", `${fmt(n(p.vol_p50))} m³`)}${row(
      "Fração com distúrbio",
      pct(n(p.disturbio_frac)),
    )}${row("Posição", p.dentro_upa === false ? "Fora da UPA" : "Dentro da UPA")}</dl>`;
  }
  if (layer.startsWith("arvores")) {
    if (p.point_count != null)
      return `<h4>${fmt(n(p.point_count), 0)} árvores</h4><dl>${row("Fora da UPA", fmt(n(p.fora), 0))}</dl><p class="pop-note">Aproxime para ver cada árvore.</p>`;
    const out = p.dentro_upa === false;
    return `<h4><i>${esc(p.especie ?? "Espécie não informada")}</i></h4>${out ? `<p class="pop-tag pop-nao_declarado">Fora do polígono autorizado</p>` : ""}<dl>${row(
      "Volume explorado",
      `${fmt(n(p.vol_explorado))} m³`,
    )}${row("Volume autorizado", `${fmt(n(p.vol_autorizado))} m³`)}${row("Data declarada", fmtDate(p.data_exploracao as string | null))}${row("Registro", esc(p.id))}</dl>`;
  }
  if (layer.startsWith("mudanca")) {
    return `<h4>Distúrbio detectado</h4><dl>${row("Área", `${fmt(n(p.area_ha))} ha`)}${row("Probabilidade", pct(n(p.prob)))}${row(
      "Posição",
      p.dentro_upa === false ? `Fora da UPA · ${fmt(n(p.dist_limite_m), 0)} m do limite` : "Dentro da UPA",
    )}${row("Janela", `${fmtDate(p.data_inicio as string)} – ${fmtDate(p.data_fim as string)}`)}${row("Método", esc(p.metodo))}</dl>`;
  }
  if (layer.startsWith("deter") || layer.startsWith("prodes")) {
    const t = layer.startsWith("deter") ? "Alerta DETER" : "PRODES";
    return `<h4>${t}</h4><dl>${p.classe != null ? row("Classe", esc(p.classe)) : ""}${p.data != null ? row("Data", fmtDate(String(p.data))) : ""}${
      p.area_ha != null ? row("Área", `${fmt(n(p.area_ha))} ha`) : ""
    }</dl>`;
  }
  return `<h4>${esc(layerInfo[layer]?.label ?? layer)}</h4>`;
}

const HATCH = (() => {
  const s = 10;
  const data = new Uint8Array(s * s * 4);
  for (let y = 0; y < s; y++)
    for (let x = 0; x < s; x++) {
      const i = (y * s + x) * 4;
      const on = (x + y) % s < 2;
      data[i] = data[i + 1] = data[i + 2] = on ? 230 : 120;
      data[i + 3] = on ? 230 : 0;
    }
  return { width: s, height: s, data };
})();

export function CaseMap({ dossier: d, focus }: { dossier: Dossier; focus?: Focus }) {
  const wrap = useRef<HTMLDivElement>(null);
  const elA = useRef<HTMLDivElement>(null);
  const elB = useRef<HTMLDivElement>(null);
  const maps = useRef<maplibregl.Map[]>([]);
  const popEl = useRef<HTMLDivElement>(null);

  const pairs = useMemo(() => {
    const out: Record<string, { pre?: Imagem; pos?: Imagem }> = {};
    for (const i of d.imagens) if (i.par) (out[i.sensor] ??= {})[i.par] = i;
    return Object.entries(out).filter(([, v]) => v.pre && v.pos) as [string, { pre: Imagem; pos: Imagem }][];
  }, [d.imagens]);
  const singles = useMemo(() => d.imagens.filter((i) => i.par && !pairs.some(([s]) => s === i.sensor)), [d.imagens, pairs]);
  const overlays = useMemo(() => d.imagens.filter((i) => !i.par), [d.imagens]);
  const hasPair = pairs.length > 0;

  const [sensor, setSensor] = useState(() => (pairs.find(([s]) => s === "CBERS-4A WPM") ?? pairs[0])?.[0] ?? "");
  const pair = pairs.find(([s]) => s === sensor)?.[1];
  const [swipe, setSwipe] = useState(50);
  const [geo, setGeo] = useState<Record<string, FeatureCollection>>({});
  const [failed, setFailed] = useState<string[]>([]);
  const [loadingLayers, setLoadingLayers] = useState(true);
  const [ready, setReady] = useState(0);
  const [enabled, setEnabled] = useState<Set<string>>(() => new Set(["upa", "buffer", "celulas", "arvores", "mudanca", "deter", "prodes"]));
  const [basemap, setBm] = useState(false);
  const [popup, setPopup] = useState<Popup>(null);
  const [highlight, setHighlight] = useState<string | null>(null);
  const [legendOpen, setLegendOpen] = useState(true);
  const layerIds = useRef<Record<string, string[]>>({});
  const vectorNames = d.camadas.filter((c) => c !== "imagem");

  /* ---- carregar camadas vetoriais ---- */
  useEffect(() => {
    const ctrl = new AbortController();
    setGeo({});
    setFailed([]);
    setLoadingLayers(true);
    Promise.all(
      vectorNames.map((n) =>
        getData<FeatureCollection>(`/cases/${encodeURIComponent(d.autex)}/layers/${n}`, ctrl.signal)
          .then((fc) => [n, fc] as const)
          .catch(() => {
            if (!ctrl.signal.aborted) setFailed((f) => [...f, n]);
            return null;
          }),
      ),
    ).then((res) => {
      if (ctrl.signal.aborted) return;
      const out: Record<string, FeatureCollection> = {};
      for (const r of res) if (r && r[1]?.features) out[r[0]] = r[1];
      setGeo(out);
      setLoadingLayers(false);
    });
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d.autex, d.camadas.join(",")]);

  /* ---- criar mapas ---- */
  useEffect(() => {
    const els = [elA.current, ...(hasPair ? [elB.current] : [])].filter(Boolean) as HTMLDivElement[];
    const ms = els.map((el) => createMap(el, { bg: "#0f2219" }));
    maps.current = ms;
    setReady(0);
    let syncing = false;
    const initBounds: [[number, number], [number, number]] = [
      [d.bbox[0], d.bbox[1]],
      [d.bbox[2], d.bbox[3]],
    ];
    ms.forEach((m, i) => {
      m.jumpTo(m.cameraForBounds(initBounds, { padding: 40 }) ?? {});
      m.on("move", () => {
        if (syncing || ms.length < 2) return;
        syncing = true;
        const o = ms[1 - i];
        o.jumpTo({ center: m.getCenter(), zoom: m.getZoom(), bearing: m.getBearing(), pitch: m.getPitch() });
        syncing = false;
        setPopup((p) => (p ? { ...p } : p));
      });
      m.on("load", () => {
        m.addImage("hatch", HATCH);
        setReady((x) => x + 1);
      });
    });
    ms[0].on("move", () => {
      if (ms.length < 2) setPopup((p) => (p ? { ...p } : p));
    });
    const ro = new ResizeObserver(() => ms.forEach((m) => m.resize()));
    if (wrap.current) ro.observe(wrap.current);
    return () => {
      ro.disconnect();
      maps.current = [];
      layerIds.current = {};
      ms.forEach((m) => m.remove());
    };
  }, [d.autex, hasPair, d.bbox]);

  const allReady = ready > 0 && ready === maps.current.length;

  /* ---- imagens de satélite / overlays ---- */
  useEffect(() => {
    if (!allReady) return;
    const ms = maps.current;
    ms.forEach((m, idx) => {
      const img = hasPair ? (idx === 0 ? pair?.pre : pair?.pos) : singles[0];
      if (img) {
        const src = m.getSource("sat") as maplibregl.ImageSource | undefined;
        const url = imageUrl(d.autex, img.png);
        if (src) src.updateImage({ url, coordinates: imageCoords(img.bounds) });
        else {
          m.addSource("sat", { type: "image", url, coordinates: imageCoords(img.bounds) });
          m.addLayer({ id: "sat", type: "raster", source: "sat", paint: { "raster-fade-duration": 0 } }, m.getLayer("uf-line") ? "uf-line" : undefined);
        }
      }
      overlays.forEach((o) => {
        const id = `ov-${o.id}`;
        if (m.getSource(id)) return;
        m.addSource(id, { type: "image", url: imageUrl(d.autex, o.png), coordinates: imageCoords(o.bounds) });
        m.addLayer({ id, type: "raster", source: id, layout: { visibility: "none" }, paint: { "raster-opacity": 0.8, "raster-fade-duration": 0 } });
      });
    });
  }, [allReady, pair, hasPair, singles, overlays, d.autex]);

  /* ---- camadas vetoriais nos mapas ---- */
  useEffect(() => {
    if (!allReady || loadingLayers) return;
    const ms = maps.current;
    for (const name of ORDER.concat(Object.keys(geo).filter((k) => !ORDER.includes(k)))) {
      const fc = geo[name];
      if (!fc) continue;
      ms.forEach((m) => {
        if (m.getSource(`v-${name}`)) return;
        layerIds.current[name] = addVectorLayers(m, name, fc, enabled.has(name));
      });
    }
    ms.forEach((m) => {
      if (!m.getSource("focus")) {
        m.addSource("focus", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        m.addLayer({ id: "focus-fill", type: "fill", source: "focus", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": "#ffffff", "fill-opacity": 0.12 } });
        m.addLayer({ id: "focus-line", type: "line", source: "focus", paint: { "line-color": "#ffffff", "line-width": 2.5 } });
        m.addLayer({
          id: "focus-pt",
          type: "circle",
          source: "focus",
          filter: ["==", ["geometry-type"], "Point"],
          paint: { "circle-radius": 11, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#ffffff", "circle-stroke-width": 2.5 },
        });
      }
      const interactive = ["celulas", "arvores", "arvores-cluster", "mudanca-fill", "deter-fill", "prodes-fill"].filter((l) => m.getLayer(l));
      m.on("click", (e) => {
        const f = m.queryRenderedFeatures(e.point, { layers: interactive.filter((l) => m.getLayer(l) && m.getLayoutProperty(l, "visibility") !== "none") });
        const top = f.sort((a, b) => interactive.indexOf(b.layer.id) - interactive.indexOf(a.layer.id))[0];
        if (!top) return setPopup(null);
        if (top.layer.id === "arvores-cluster") {
          const src = m.getSource("v-arvores") as maplibregl.GeoJSONSource;
          void src.getClusterExpansionZoom(Number(top.properties.cluster_id)).then((z) => m.easeTo({ center: e.lngLat, zoom: z }));
        }
        setPopup({ lngLat: [e.lngLat.lng, e.lngLat.lat], html: popupHtml(top.layer.id, top.properties) });
      });
      m.on("mousemove", (e) => {
        const hit = interactive.some((l) => m.getLayer(l) && m.getLayoutProperty(l, "visibility") !== "none") &&
          m.queryRenderedFeatures(e.point, { layers: interactive.filter((l) => m.getLayoutProperty(l, "visibility") !== "none") }).length > 0;
        m.getCanvas().style.cursor = hit ? "pointer" : "";
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allReady, loadingLayers, geo]);

  /* ---- visibilidade ---- */
  useEffect(() => {
    if (!allReady) return;
    maps.current.forEach((m) => {
      for (const [name, ids] of Object.entries(layerIds.current))
        ids.forEach((id) => m.getLayer(id) && m.setLayoutProperty(id, "visibility", enabled.has(name) ? "visible" : "none"));
      overlays.forEach((o) => m.getLayer(`ov-${o.id}`) && m.setLayoutProperty(`ov-${o.id}`, "visibility", enabled.has(`ov-${o.id}`) ? "visible" : "none"));
      setBasemap(m, basemap);
    });
  }, [enabled, allReady, overlays, basemap, geo]);

  /* ---- popup posicionado sobre ambos os mapas ---- */
  useEffect(() => {
    const el = popEl.current;
    const m = maps.current[0];
    if (!el || !m || !popup) return;
    const p = m.project(popup.lngLat);
    const w = wrap.current?.clientWidth ?? 800;
    el.style.transform = `translate(${Math.round(p.x)}px, ${Math.round(p.y)}px)`;
    el.classList.toggle("below", p.y < 250);
    const inner = el.firstElementChild as HTMLElement | null;
    if (inner) {
      const half = 160;
      const shift = p.x < half + 8 ? half + 8 - p.x : p.x > w - half - 8 ? w - half - 8 - p.x : 0;
      inner.style.setProperty("--dx", `${Math.round(shift)}px`);
    }
  });

  const fit = useCallback((b: maplibregl.LngLatBounds, maxZoom = 16) => {
    const m = maps.current[0];
    if (!m || b.isEmpty()) return;
    m.fitBounds(b, { padding: 70, maxZoom, duration: 900 });
  }, []);

  const resetView = () => {
    const upa = geo.upa;
    const b = upa ? boundsOf(upa) : new maplibregl.LngLatBounds([d.bbox[0], d.bbox[1]], [d.bbox[2], d.bbox[3]]);
    if (geo.buffer) b.extend(boundsOf(geo.buffer));
    fit(b);
    setHighlight(null);
    setPopup(null);
    maps.current.forEach((m) => (m.getSource("focus") as maplibregl.GeoJSONSource | undefined)?.setData({ type: "FeatureCollection", features: [] }));
  };

  /* ---- foco vindo de evidência ---- */
  useEffect(() => {
    if (!focus || !allReady || loadingLayers) return;
    const { ev } = focus;
    const camada = ev.camada ?? "";
    const img = d.imagens.find((i) => i.id === camada);
    if (img) {
      if (img.par) {
        if (pairs.some(([s]) => s === img.sensor)) setSensor(img.sensor);
        setSwipe(img.par === "pos" ? 8 : 92);
      } else setEnabled((s) => new Set(s).add(`ov-${img.id}`));
      setHighlight(img.rotulo);
    }
    const fc = geo[camada];
    if (!fc) return;
    setEnabled((s) => new Set(s).add(camada));
    const filtro = ev.filtro ?? null;
    const feats: Feature[] = fc.features.filter((f) => !filtro || Object.entries(filtro).every(([k, v]) => f.properties?.[k] === v));
    const sel: FeatureCollection = { type: "FeatureCollection", features: feats };
    maps.current.forEach((m) => (m.getSource("focus") as maplibregl.GeoJSONSource | undefined)?.setData(sel));
    setHighlight(`${layerInfo[camada]?.label ?? camada}${filtro ? ` · ${feats.length} feição(ões)` : ""}`);
    setPopup(null);
    fit(boundsOf(sel), camada === "arvores" ? 16 : 15.5);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus, allReady, loadingLayers]);

  /* ---- arrastar o divisor ---- */
  const dragging = useRef(false);
  const moveTo = (clientX: number) => {
    const r = wrap.current?.getBoundingClientRect();
    if (!r) return;
    setSwipe(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)));
  };

  const toggle = (k: string) =>
    setEnabled((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  const present = DISPLAY.filter((n) => geo[n]).concat(Object.keys(geo).filter((k) => !DISPLAY.includes(k)));
  const counts = (n: string) => geo[n]?.features.length ?? 0;
  const celCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const f of geo.celulas?.features ?? []) {
      const k = String(f.properties?.classe);
      c[k] = (c[k] ?? 0) + 1;
    }
    return c;
  }, [geo.celulas]);
  const foraCount = useMemo(() => geo.arvores?.features.filter((f) => f.properties?.dentro_upa === false).length ?? 0, [geo.arvores]);

  const noImagery = d.imagens.length === 0 || !d.analise_imagem;

  return (
    <div className="casemap">
      <div className="casemap-bar">
        {hasPair ? (
          <div className="seg" role="radiogroup" aria-label="Sensor da comparação">
            {pairs.map(([s]) => (
              <button key={s} type="button" role="radio" aria-checked={s === sensor} className={s === sensor ? "on" : ""} onClick={() => setSensor(s)}>
                {sensorShort[s] ?? s}
              </button>
            ))}
          </div>
        ) : (
          <span className="bar-note">
            <Icon name="image" size={15} />
            {noImagery ? "Imagem de satélite não analisada para esta autorização" : "Sem par antes/depois disponível"}
          </span>
        )}
        <div className="bar-right">
          {highlight && (
            <span className="focus-chip">
              <Icon name="target" size={14} /> {highlight}
            </span>
          )}
          <button type="button" className="ghost" onClick={resetView}>
            Enquadrar UPA
          </button>
        </div>
      </div>

      <div
        ref={wrap}
        className="swipe"
        onPointerMove={(e) => dragging.current && moveTo(e.clientX)}
        onPointerUp={() => (dragging.current = false)}
        onPointerLeave={() => (dragging.current = false)}
      >
        <div ref={elA} className="map-fill" />
        {hasPair && <div ref={elB} className="map-fill after" style={{ clipPath: `inset(0 0 0 ${swipe}%)` }} />}

        {hasPair && pair && (
          <>
            <div className="img-label left" style={{ opacity: swipe < 18 ? 0 : 1 }}>
              <b>Antes</b>
              <span>
                {pair.pre.sensor} · {fmtPeriod(pair.pre.data)}
              </span>
            </div>
            <div className="img-label right" style={{ opacity: swipe > 82 ? 0 : 1 }}>
              <b>Depois</b>
              <span>
                {pair.pos.sensor} · {fmtPeriod(pair.pos.data)}
              </span>
            </div>
            <div className="divider" style={{ left: `${swipe}%` }}>
              <div
                className="knob"
                role="slider"
                tabIndex={0}
                aria-label="Divisor antes e depois"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(swipe)}
                aria-valuetext={`${Math.round(swipe)}% da imagem anterior visível`}
                onPointerDown={(e) => {
                  dragging.current = true;
                  (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
                }}
                onPointerMove={(e) => dragging.current && moveTo(e.clientX)}
                onPointerUp={() => (dragging.current = false)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowLeft") setSwipe((s) => Math.max(0, s - 5));
                  if (e.key === "ArrowRight") setSwipe((s) => Math.min(100, s + 5));
                }}
              >
                <Icon name="swap" size={18} />
              </div>
            </div>
          </>
        )}
        {!hasPair && singles[0] && (
          <div className="img-label left">
            <b>Imagem</b>
            <span>{singles[0].rotulo}</span>
          </div>
        )}
        {noImagery && (
          <div className="map-empty">
            <Icon name="doc" size={18} />
            <div>
              <b>Análise apenas documental</b>
              <span>
                {present.length
                  ? "Exibindo os limites autorizados. Para comparar imagens antes e depois, use “Analisar autorização”."
                  : "Sem geometria publicada para esta autorização; o enquadramento usa o retângulo informado."}
              </span>
            </div>
          </div>
        )}

        {popup && (
          <div ref={popEl} className="mpop-anchor">
            <div className="mpop">
              <button type="button" className="mpop-x" aria-label="Fechar detalhe" onClick={() => setPopup(null)}>
                <Icon name="close" size={14} />
              </button>
              <div dangerouslySetInnerHTML={{ __html: popup.html }} />
            </div>
          </div>
        )}

        <div className={legendOpen ? "legend-float" : "legend-float closed"}>
          <button type="button" className="legend-toggle" aria-expanded={legendOpen} onClick={() => setLegendOpen((v) => !v)}>
            <Icon name="layers" size={16} /> Camadas
            <Icon name="chevron" size={14} className="caret" />
          </button>
          {legendOpen && (
            <div className="legend-body">
              {present.map((n) => (
                <div key={n}>
                  <label className={enabled.has(n) ? "lg on" : "lg"}>
                    <input type="checkbox" checked={enabled.has(n)} onChange={() => toggle(n)} />
                    <i className={`sw sw-${layerInfo[n]?.kind ?? "line"}`} style={{ "--c": layerInfo[n]?.color ?? "#fff" } as React.CSSProperties} />
                    <span>{layerInfo[n]?.label ?? n}</span>
                    <em>{n === "arvores" && foraCount ? `${fmt(counts(n), 0)} · ${foraCount} fora` : n === "celulas" ? "" : fmt(counts(n), 0)}</em>
                  </label>
                  {n === "celulas" && enabled.has("celulas") && (
                    <div className="legend-classes" aria-label="Classes das células">
                      {cellClasses
                        .filter((c) => c.id !== "sem_atividade")
                        .map((c) => (
                          <span key={c.id}>
                            <i className={`cls cls-${c.id}`} style={{ background: c.color }} />
                            {c.label}
                            <em>{fmt(celCounts[c.id] ?? 0, 0)}</em>
                          </span>
                        ))}
                    </div>
                  )}
                </div>
              ))}
              {overlays.map((o) => (
                <label key={o.id} className={enabled.has(`ov-${o.id}`) ? "lg on" : "lg"}>
                  <input type="checkbox" checked={enabled.has(`ov-${o.id}`)} onChange={() => toggle(`ov-${o.id}`)} />
                  <i className={`sw sw-raster ${o.id === "dndvi" ? "dndvi" : "prob"}`} />
                  <span>{o.rotulo}</span>
                </label>
              ))}
              <label className={basemap ? "lg on" : "lg"}>
                <input type="checkbox" checked={basemap} onChange={(e) => setBm(e.target.checked)} />
                <i className="sw sw-raster esri" />
                <span>Fundo Esri (online)</span>
              </label>
            </div>
          )}
        </div>        <div className="zoom">
          <button type="button" aria-label="Aproximar" onClick={() => maps.current[0]?.zoomIn()}>
            <Icon name="plus" size={16} />
          </button>
          <button type="button" aria-label="Afastar" onClick={() => maps.current[0]?.zoomOut()}>
            <svg width="16" height="16" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
              <path d="M5 12h14" />
            </svg>
          </button>
        </div>
        {basemap && <div className="attribution">{ESRI_ATTR}</div>}
        {loadingLayers && vectorNames.length > 0 && (
          <div className="map-loading">
            <span className="spinner small" /> Carregando camadas…
          </div>
        )}
      </div>

      {failed.length > 0 && (
        <p className="layer-error" role="alert">
          <Icon name="alert" size={14} /> Camadas indisponíveis: {failed.map((f) => layerInfo[f]?.label ?? f).join(", ")}.
        </p>
      )}    </div>
  );
}
