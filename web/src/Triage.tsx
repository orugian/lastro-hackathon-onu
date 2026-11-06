import { useDeferredValue, useMemo, useState } from "react";
import type { CaseSummary, Index } from "./types";
import { fmt, fmtVol, priority, priorityColor, scoreInt, sortFlags, staticMode, titleCase, useData } from "./data";
import { OverviewMap } from "./OverviewMap";
import { Empty, ErrorState, Icon, Loading, SimBadge } from "./ui";

const totalLabels: [string, string][] = [
  ["autorizacoes_avaliadas", "autorizações avaliadas"],
  ["com_indicio", "com ao menos um indício"],
  ["com_imagem", "com imagem analisada"],
  ["arvores_if100", "árvores declaradas (IF100)"],
  ["volume_declarado_total_m3", "m³ declarados"],
];
const PAGE = 40;
const flagShort: Record<string, string> = {
  A: "Volume sem lastro",
  B: "Distúrbio não declarado",
  C: "Árvores fora da UPA",
  D: "Volume acima do autorizado",
  E: "Fora da validade",
  F2: "Área acima da autorizada",
  F6: "UC / TI / embargo",
};

function ScoreBar({ score }: { score: number }) {
  const p = priority(score);
  return (
    <div className="score">
      <div className="score-track" aria-hidden="true">
        <span style={{ width: `${Math.max(2, scoreInt(score))}%`, background: priorityColor[p] }} />
      </div>
      <b className={`score-n p-${p}`}>{scoreInt(score)}</b>
    </div>
  );
}

function VolumeTriple({ c }: { c: CaseSummary }) {
  return (
    <dl className="vtriple">
      <div>
        <dt>Autorizado</dt>
        <dd>{fmtVol(c.volume_autorizado_m3)}</dd>
      </div>
      <div>
        <dt>Declarado</dt>
        <dd>{fmtVol(c.volume_declarado_explorado_m3)}</dd>
      </div>
      <div>
        <dt>Estimado p50</dt>
        <dd>{c.analise_imagem ? fmtVol(c.volume_estimado_m3.p50) : "—"}</dd>
      </div>
    </dl>
  );
}

function CaseRow({ c, rank, hovered, onHover }: { c: CaseSummary; rank: number; hovered: boolean; onHover: (a: string | null) => void }) {
  const ind = sortFlags(c.flags).filter((f) => f.status === "indicio");
  return (
    <li>
      <a
        className={hovered ? "case-row hov" : "case-row"}
        href={`#/caso/${encodeURIComponent(c.autex)}`}
        onMouseEnter={() => onHover(c.autex)}
        onMouseLeave={() => onHover(null)}
      >
        <span className="rank">{rank}</span>
        <div className="case-main">
          <div className="case-id">
            <code>{c.autex}</code>
            <span className="tipo">{c.tipo}</span>
            {c.analise_imagem ? (
              <span className="imgflag" title="Imagem de satélite analisada">
                <Icon name="image" size={14} /> imagem
              </span>
            ) : (
              <span className="imgflag off" title="Somente cruzamento documental">
                <Icon name="doc" size={14} /> documental
              </span>
            )}
          </div>
          <div className="case-place">
            {titleCase(c.municipio)} · {c.uf}
          </div>
          <div className="chips">
            {ind.length ? (
              ind.map((f) => (
                <span key={f.codigo} className={`chip sev-${f.severidade}`} title={f.titulo}>
                  <b>{f.codigo}</b> {flagShort[f.codigo] ?? f.titulo}
                </span>
              ))
            ) : (
              <span className="chip none">Sem indício nas regras avaliadas</span>
            )}
          </div>
          <VolumeTriple c={c} />
        </div>
        <ScoreBar score={c.score} />
      </a>
    </li>
  );
}

export function Triage() {
  const { data, error, retry } = useData<Index>("/index");
  const [uf, setUf] = useState("");
  const [tipo, setTipo] = useState("");
  const [flag, setFlag] = useState("");
  const [onlyImg, setOnlyImg] = useState(false);
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const [hovered, setHovered] = useState<string | null>(null);
  const dq = useDeferredValue(q.trim().toLowerCase());

  const all = useMemo(() => [...(data?.casos ?? [])].sort((a, b) => b.score - a.score), [data]);
  const opts = useMemo(
    () => ({
      ufs: [...new Set(all.map((c) => c.uf))].sort(),
      tipos: [...new Set(all.map((c) => c.tipo))].sort(),
      flags: [...new Map(all.flatMap((c) => c.flags).map((f) => [f.codigo, f.titulo])).entries()].sort(),
    }),
    [all],
  );
  const cases = useMemo(
    () =>
      all.filter(
        (c) =>
          (!uf || c.uf === uf) &&
          (!tipo || c.tipo === tipo) &&
          (!flag || c.flags.some((f) => f.codigo === flag && f.status === "indicio")) &&
          (!onlyImg || c.analise_imagem) &&
          (!dq || c.autex.toLowerCase().includes(dq) || c.municipio.toLowerCase().includes(dq)),
      ),
    [all, uf, tipo, flag, onlyImg, dq],
  );
  const filtered = uf || tipo || flag || onlyImg || dq;
  const reset = () => {
    setUf("");
    setTipo("");
    setFlag("");
    setOnlyImg(false);
    setQ("");
    setLimit(PAGE);
  };

  if (!data) return error ? <ErrorState message={error} retry={retry} /> : <Loading label="Carregando autorizações do polo…" />;
  const simulated = data.casos.some((c) => c.source_mode === "simulado");

  return (
    <main className="triage">
      <div className="triage-head">
        <div className="th-title">
          <h1>Triagem territorial</h1>
          <p className="totals">
            {totalLabels
              .filter(([k]) => typeof data.totais[k] === "number")
              .map(([k, label], i) => (
                <span key={k}>
                  {i > 0 && <i aria-hidden="true">·</i>}
                  <b>{fmt(data.totais[k], 0)}</b> {label}
                </span>
              ))}
          </p>
        </div>
        <div className="th-meta">
          <SimBadge show={simulated} />
          <span>
            {data.polo} · gerado em {new Date(data.gerado_em).toLocaleDateString("pt-BR")}
            {staticMode && " · acervo local"}
          </span>
        </div>
      </div>

      <div className="triage-grid">
        <OverviewMap cases={cases} hovered={hovered} onHover={setHovered} />
        <aside className="ranked" aria-label="Autorizações ranqueadas">
          <div className="filters">
            <label className="search">
              <span className="sr-only">Buscar</span>
              <input value={q} onChange={(e) => (setQ(e.target.value), setLimit(PAGE))} placeholder="Buscar AUTEX ou município" spellCheck={false} />
            </label>
            <div className="frow">
              <select aria-label="UF" value={uf} onChange={(e) => (setUf(e.target.value), setLimit(PAGE))}>
                <option value="">Todas as UF</option>
                {opts.ufs.map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
              <select aria-label="Tipo de autorização" value={tipo} onChange={(e) => (setTipo(e.target.value), setLimit(PAGE))}>
                <option value="">Todos os tipos</option>
                {opts.tipos.map((v) => (
                  <option key={v} value={v}>
                    {v === "POA" ? "POA · manejo" : `${v} · corte raso`}
                  </option>
                ))}
              </select>
              <select aria-label="Indício" value={flag} onChange={(e) => (setFlag(e.target.value), setLimit(PAGE))}>
                <option value="">Qualquer indício</option>
                {opts.flags.map(([k, t]) => (
                  <option key={k} value={k}>
                    {k} · {t}
                  </option>
                ))}
              </select>
            </div>
            <div className="frow between">
              <label className="check">
                <input type="checkbox" checked={onlyImg} onChange={(e) => (setOnlyImg(e.target.checked), setLimit(PAGE))} />
                Só com imagem analisada
              </label>
              <span className="count">
                {fmt(cases.length, 0)} de {fmt(all.length, 0)}
                {filtered && (
                  <button type="button" className="link" onClick={reset}>
                    limpar
                  </button>
                )}
              </span>
            </div>
          </div>
          <div className="list-cols" aria-hidden="true">
            <span>Autorização · indícios · volumes em m³</span>
            <span>Prioridade</span>
          </div>
          {cases.length === 0 ? (
            <Empty title="Nenhuma autorização com esses filtros">
              <p>Amplie os critérios para voltar a ver o ranking.</p>
              <button type="button" onClick={reset}>
                Limpar filtros
              </button>
            </Empty>
          ) : (
            <ol className="case-list">
              {cases.slice(0, limit).map((c, i) => (
                <CaseRow key={c.autex} c={c} rank={i + 1} hovered={hovered === c.autex} onHover={setHovered} />
              ))}
              {cases.length > limit && (
                <li className="more">
                  <button type="button" onClick={() => setLimit((l) => l + PAGE * 2)}>
                    Mostrar mais {fmt(Math.min(PAGE * 2, cases.length - limit), 0)} de {fmt(cases.length - limit, 0)} restantes
                  </button>
                </li>
              )}
            </ol>
          )}
        </aside>
      </div>
    </main>
  );
}
