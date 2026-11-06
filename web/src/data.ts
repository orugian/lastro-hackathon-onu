import { useEffect, useState } from "react";
import type { CaseSummary, FlagResumo, Severidade, Status } from "./types";

export let staticMode = false;
let ready: Promise<void> | undefined;

/** Detecta se a API local responde; caso contrário, usa os arquivos estáticos de web/public/mock. */
export function initialize() {
  return (ready ??= fetch("/api/health", { signal: AbortSignal.timeout(2500) })
    .then((r) => {
      if (!r.ok) throw Error("health");
    })
    .catch(() => {
      staticMode = true;
    }));
}

function staticUrl(path: string) {
  if (path.startsWith("/index")) return "/mock/index.json";
  if (path.startsWith("/metrics/")) return `/mock${path}.json`;
  const layer = path.match(/^\/cases\/([^/]+)\/layers\/([^/]+)$/);
  if (layer) return `/mock/cases/${layer[1]}/${layer[2]}.geojson`;
  const cs = path.match(/^\/cases\/([^/]+)$/);
  if (cs) return `/mock/cases/${cs[1]}/dossier.json`;
  return `/mock${path}`;
}

export class HttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function getData<T>(path: string, signal?: AbortSignal): Promise<T> {
  await initialize();
  const url = staticMode ? staticUrl(path) : `/api${path}`;
  let r: Response;
  try {
    r = await fetch(url, { signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new HttpError(0, "Sem conexão com o servidor local. Verifique se a API está em execução.");
  }
  if (r.status === 404) throw new HttpError(404, "Registro não encontrado no acervo processado.");
  if (!r.ok) throw new HttpError(r.status, "Não foi possível carregar estes dados agora.");
  return r.json() as Promise<T>;
}

export function imageUrl(autex: string, png: string) {
  const file = png.split(/[\\/]/).pop();
  return `${staticMode ? "/mock" : "/api"}/cases/${encodeURIComponent(autex)}/img/${file}`;
}

export function printableUrl(autex: string) {
  return `/api/cases/${encodeURIComponent(autex)}/dossier.html`;
}

export function useData<T>(path: string | null) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!path) return;
    const ctrl = new AbortController();
    setData(undefined);
    setError("");
    setNotFound(false);
    getData<T>(path, ctrl.signal)
      .then(setData)
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setError(e instanceof Error ? e.message : "Erro inesperado.");
        setNotFound(e instanceof HttpError && e.status === 404);
      });
    return () => ctrl.abort();
  }, [path, revision]);
  return { data, error, notFound, retry: () => setRevision((x) => x + 1) };
}

/* ---------- formatação ---------- */
const nf = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });

export const fmt = (v: number | null | undefined, digits?: 0) =>
  v == null || Number.isNaN(v) ? "—" : digits === 0 ? nf0.format(v) : nf.format(v);

export const fmtVol = (v: number | null | undefined) =>
  v == null ? "—" : v >= 1000 ? nf0.format(v) : nf.format(v);

export const pct = (v: number | null | undefined, digits = 0) =>
  v == null ? "—" : `${(v * 100).toLocaleString("pt-BR", { maximumFractionDigits: digits })}%`;

export function fmtDate(iso: string | null | undefined) {
  if (!iso) return "—";
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso;
}

export function fmtPeriod(s: string | null | undefined) {
  if (!s) return "data não informada";
  const parts = s.split("/");
  if (parts.length === 2) {
    const [a, b] = parts.map((p) => p.match(/^(\d{4})-(\d{2})/));
    if (a && b) return `${a[2]}/${a[1]} – ${b[2]}/${b[1]}`;
  }
  return fmtDate(s);
}

export const scoreInt = (s: number) => Math.round(Math.max(0, Math.min(1, s)) * 100);

export type Priority = "alta" | "media" | "baixa";
export function priority(score: number): Priority {
  return score >= 0.6 ? "alta" : score >= 0.3 ? "media" : "baixa";
}
export const priorityLabel: Record<Priority, string> = {
  alta: "Prioridade alta",
  media: "Prioridade média",
  baixa: "Prioridade baixa",
};
export const priorityColor: Record<Priority, string> = {
  alta: "#b91c1c",
  media: "#d97706",
  baixa: "#7f9c6f",
};

export const statusLabel: Record<Status, string> = {
  indicio: "Indício",
  sem_indicio: "Sem indício",
  inconclusivo: "Inconclusivo",
  nao_avaliado: "Não avaliado",
};
export const severityLabel: Record<Severidade, string> = {
  alta: "severidade alta",
  media: "severidade média",
  baixa: "severidade baixa",
  info: "informativo",
};

const statusRank: Record<Status, number> = { indicio: 0, inconclusivo: 1, sem_indicio: 2, nao_avaliado: 3 };
const sevRank: Record<Severidade, number> = { alta: 0, media: 1, baixa: 2, info: 3 };
export function sortFlags<T extends FlagResumo>(flags: T[]) {
  return [...flags].sort(
    (a, b) => statusRank[a.status] - statusRank[b.status] || sevRank[a.severidade] - sevRank[b.severidade],
  );
}

export const tipoLabel = (c: Pick<CaseSummary, "tipo">) =>
  c.tipo === "POA" ? "Manejo seletivo (POA/PMFS)" : c.tipo === "ASV" ? "Corte raso (ASV)" : "Corte raso (UAS)";

export function titleCase(s: string) {
  return s
    .toLowerCase()
    .replace(/(^|[\s(/-])(\p{L})/gu, (_, p: string, c: string) => p + c.toUpperCase())
    .replace(/\b(De|Do|Da|Dos|Das|E)\b/g, (w) => w.toLowerCase())
    .replace(/\(Mock\)/i, "(mock)");
}
