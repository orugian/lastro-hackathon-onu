import { useEffect, useState } from "react";
export let staticMode = false;
let ready: Promise<void> | undefined;
export function initialize() {
  return (ready ??= fetch("/api/health", { signal: AbortSignal.timeout(2500) })
    .then((r) => {
      if (!r.ok) throw Error();
    })
    .catch(() => {
      staticMode = true;
    }));
}
export async function getData<T>(path: string): Promise<T> {
  await initialize();
  const file = path
    .replace(/^\/cases\/([^/]+)$/, "/cases/$1/dossier")
    .replace("/layers/", "/");
  const url = staticMode
    ? `/mock${file}${path.includes("/layers/") ? ".geojson" : ".json"}`
    : `/api${path}`;
  const r = await fetch(url);
  if (!r.ok)
    throw Error("Não foi possível carregar estes dados. Tente novamente.");
  return r.json();
}
export function imageUrl(autex: string, png: string) {
  return `${staticMode ? "/mock" : "/api"}/cases/${encodeURIComponent(autex)}/img/${png.split(/[\\/]/).pop()}`;
}
export function useData<T>(path: string) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setData(undefined);
    setError("");
    getData<T>(path)
      .then((d) => {
        if (active) setData(d);
      })
      .catch((e) => {
        if (active) setError(String(e.message));
      });
    return () => {
      active = false;
    };
  }, [path, revision]);
  return { data, error, retry: () => setRevision((x) => x + 1) };
}
export const number = (v: number | null | undefined) =>
  v == null
    ? "Não avaliado"
    : v.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
export const percent = (v: number | null | undefined) =>
  v == null ? "Não avaliado" : `${number(v * 100)}%`;
export const status: Record<string, string> = {
  indicio: "Indício",
  sem_indicio: "Sem indício",
  inconclusivo: "Inconclusivo",
  nao_avaliado: "Não avaliado",
};
