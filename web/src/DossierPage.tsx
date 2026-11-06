import { useState } from "react";
import type { Dossier, Evidencia, Flag } from "./types";
import { fmt, fmtDate, fmtVol, pct, printableUrl, priority, priorityColor, priorityLabel, scoreInt, severityLabel, sortFlags, staticMode, statusLabel, tipoLabel, titleCase, useData } from "./data";
import { CaseMap, layerInfo, type Focus } from "./CaseMap";
import { VolumeChart } from "./Charts";
import { ErrorState, ExperimentalSeal, Icon, Loading, SimBadge } from "./ui";

const fonteLabel: Record<string, string> = {
  if100: "IF100",
  s2: "Sentinel-2",
  cbers: "CBERS-4A",
  deter: "DETER",
  prodes: "PRODES",
  pamgia: "Sinaflor",
  dof: "DOF",
  sinaflor: "Sinaflor",
};

function evidenceTarget(ev: Evidencia, d: Dossier) {
  if (!ev.camada) return null;
  if (d.camadas.includes(ev.camada)) return layerInfo[ev.camada]?.label ?? ev.camada;
  const img = d.imagens.find((i) => i.id === ev.camada);
  return img ? img.rotulo : null;
}

function FlagItem({ f, d, onFocus, open, setOpen }: { f: Flag; d: Dossier; onFocus: (e: Evidencia) => void; open: boolean; setOpen: (v: boolean) => void }) {
  const isInd = f.status === "indicio";
  return (
    <li className={`flag st-${f.status}${open ? " open" : ""}`}>
      <button type="button" className="flag-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className={`fcode${isInd ? ` sev-${f.severidade}` : ""}`}>{f.codigo}</span>
        <span className="ftitle">
          <b>{f.titulo}</b>
          <span className="fmeta">
            <span className={`status s-${f.status}`}>{statusLabel[f.status]}</span>
            {isInd && <span>{severityLabel[f.severidade]}</span>}
            <span>confiança {pct(f.confianca)}</span>
          </span>
        </span>
        <Icon name="chevron" size={16} className="caret" />
      </button>
      {open && (
        <div className="flag-body">
          <p className="rule">
            <span>Regra</span>
            {f.regra}
          </p>
          {(f.volume_m3?.p50 != null || f.area_ha != null) && (
            <p className="fnums">
              {f.volume_m3?.p50 != null && (
                <span>
                  Volume envolvido <b>{fmtVol(f.volume_m3.p50)} m³</b>
                  {f.volume_m3.p10 != null && f.volume_m3.p90 != null && (
                    <small>
                      {" "}
                      (p10–p90: {fmtVol(f.volume_m3.p10)}–{fmtVol(f.volume_m3.p90)})
                    </small>
                  )}
                </span>
              )}
              {f.area_ha != null && (
                <span>
                  Área <b>{fmt(f.area_ha)} ha</b>
                </span>
              )}
            </p>
          )}
          {f.evidencias.length === 0 ? (
            <p className="muted small">Nenhuma evidência adicional registrada.</p>
          ) : (
            <ul className="evidences">
              {f.evidencias.map((ev, i) => {
                const target = evidenceTarget(ev, d);
                const body = (
                  <>
                    <span className="ev-text">
                      {ev.descricao}
                      {ev.valor != null && (
                        <b className="ev-val">
                          {fmt(ev.valor)} {ev.unidade ?? ""}
                        </b>
                      )}
                    </span>
                    <span className="ev-meta">
                      {ev.fonte && <span>{fonteLabel[ev.fonte] ?? ev.fonte}</span>}
                      {target && (
                        <span className="ev-go">
                          <Icon name="target" size={13} /> ver no mapa: {target}
                        </span>
                      )}
                    </span>
                  </>
                );
                return (
                  <li key={i}>
                    {target ? (
                      <button type="button" className="ev clickable" onClick={() => onFocus(ev)}>
                        {body}
                      </button>
                    ) : (
                      <div className="ev">{body}</div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

function Facts({ d }: { d: Dossier }) {
  return (
    <dl className="facts">
      <div>
        <dt>Área autorizada</dt>
        <dd>{d.area_autorizada_ha != null ? `${fmt(d.area_autorizada_ha)} ha` : "—"}</dd>
      </div>
      <div>
        <dt>Validade</dt>
        <dd>
          {fmtDate(d.validade.inicio)} – {fmtDate(d.validade.fim)}
        </dd>
      </div>
      <div>
        <dt>Situação</dt>
        <dd>{d.situacao ?? "—"}</dd>
      </div>
      <div>
        <dt>Árvores declaradas</dt>
        <dd>{fmt(d.n_arvores_declaradas, 0)}</dd>
      </div>
      <div>
        <dt>Distúrbio detectado</dt>
        <dd>
          {d.area_disturbio_ha != null ? `${fmt(d.area_disturbio_ha)} ha` : "—"}
          {d.area_disturbio_fora_ha ? <small> · {fmt(d.area_disturbio_fora_ha)} ha fora</small> : null}
        </dd>
      </div>
    </dl>
  );
}

export function DossierPage({ autex, openAnalyze }: { autex: string; openAnalyze: (a: string) => void }) {
  const { data: d, error, notFound, retry } = useData<Dossier>(`/cases/${encodeURIComponent(autex)}`);
  const [focus, setFocus] = useState<Focus>();
  const [open, setOpen] = useState<Record<string, boolean>>({});

  if (!d) {
    if (!error) return <Loading label={`Carregando dossiê ${autex}…`} />;
    return notFound ? (
      <ErrorState title="Dossiê não encontrado" message={`A autorização ${autex} ainda não foi processada neste acervo.`}>
        {!staticMode && (
          <button type="button" className="primary" onClick={() => openAnalyze(autex)}>
            Analisar esta autorização
          </button>
        )}
        <a className="button" href="#/">
          Voltar à triagem
        </a>
      </ErrorState>
    ) : (
      <ErrorState message={error} retry={retry} />
    );
  }

  const flags = sortFlags(d.flags_detalhe);
  const p = priority(d.score);
  const nInd = flags.filter((f) => f.status === "indicio").length;
  const isOpen = (f: Flag) => open[f.codigo] ?? f.status === "indicio";
  const species = [...d.especies].sort((a, b) => (b.volume_explorado_m3 ?? 0) - (a.volume_explorado_m3 ?? 0));

  return (
    <main className="dossier">
      <div className="dossier-head">
        <div className="dh-left">
          <a className="back" href="#/">
            <Icon name="back" size={15} /> Triagem
          </a>
          <div className="dh-title">
            <h1>
              <span className="h1-pre">AUTEX</span> <code>{d.autex}</code>
            </h1>
            <span className="tipo big">{tipoLabel(d)}</span>
            <SimBadge show={d.source_mode === "simulado"} />
          </div>
          <p className="dh-sub">
            {titleCase(d.municipio)} / {d.uf} · {d.area_autorizada_ha != null ? `${fmt(d.area_autorizada_ha)} ha` : "área não informada"} · validade {fmtDate(d.validade.inicio)} – {fmtDate(d.validade.fim)}
            {d.situacao ? ` · ${d.situacao}` : ""}
          </p>
          <ExperimentalSeal compact />
        </div>
        <div className="dh-right">
          <div className="prio" style={{ "--pc": priorityColor[p] } as React.CSSProperties}>
            <span className="prio-n">{scoreInt(d.score)}</span>
            <span className="prio-t">
              <b>{priorityLabel[p]}</b>
              <small>
                {nInd} indício{nInd === 1 ? "" : "s"} · score de triagem, não probabilidade
              </small>
            </span>
          </div>
          <div className="dh-actions">
            <a className="button" target="_blank" rel="noreferrer" href={printableUrl(d.autex)} onClick={(e) => staticMode && (e.preventDefault(), window.print())}>
              <Icon name="print" size={16} /> Dossiê imprimível
            </a>
            {d.score >= 0.7 && nInd > 0 && !staticMode && (
              <a className="button ibama" href="#/comunicacoes" title="Score ≥ 70: protocolo de comunicação gerado automaticamente">
                <Icon name="external" size={16} /> Comunicação ao IBAMA
              </a>
            )}
          </div>
        </div>
      </div>

      <div className="dossier-grid">
        <section className="map-col" aria-label="Mapa do caso">
          <CaseMap dossier={d} focus={focus} />
        </section>

        <aside className="panel">
          <section>
            <h2>O volume declarado tem lastro?</h2>
            <VolumeChart data={d} />
            {!d.analise_imagem && (
              <p className="note">
                <Icon name="info" size={14} /> Imagem não analisada: o confronto com a floresta observada ainda não foi feito. Os indícios abaixo usam apenas os registros documentais.
              </p>
            )}
          </section>

          <section>
            <div className="sec-head">
              <h2>Indícios</h2>
              <span className="muted small">
                {nInd} de {flags.length} regras com indício
              </span>
            </div>
            {flags.length ? (
              <ul className="flags">
                {flags.map((f) => (
                  <FlagItem key={f.codigo} f={f} d={d} open={isOpen(f)} setOpen={(v) => setOpen((o) => ({ ...o, [f.codigo]: v }))} onFocus={(ev) => setFocus({ ev, nonce: Date.now() })} />
                ))}
              </ul>
            ) : (
              <p className="muted">Nenhuma regra avaliada para esta autorização.</p>
            )}
          </section>

          {d.linha_do_tempo.length > 0 && (
            <section>
              <h2>Linha do tempo</h2>
              <ol className="timeline">
                {[...d.linha_do_tempo]
                  .sort((a, b) => a.data.localeCompare(b.data))
                  .map((e, i) => (
                    <li key={i}>
                      <time>{fmtDate(e.data)}</time>
                      <span>
                        {e.evento}
                        {e.fonte && <small> · {fonteLabel[e.fonte] ?? e.fonte}</small>}
                      </span>
                    </li>
                  ))}
              </ol>
            </section>
          )}
          <section>
            <h2>Dados da autorização</h2>
            <Facts d={d} />
          </section>

          {species.length > 0 && (
            <section>
              <h2>Espécies</h2>
              <table className="species">
                <thead>
                  <tr>
                    <th>Espécie</th>
                    <th>Árv.</th>
                    <th>Autorizado</th>
                    <th>Explorado</th>
                  </tr>
                </thead>
                <tbody>
                  {species.slice(0, 12).map((s) => (
                    <tr key={s.nome_cientifico}>
                      <td>
                        <i>{s.nome_cientifico}</i>
                        {s.nome_popular && <small>{s.nome_popular}</small>}
                      </td>
                      <td>{fmt(s.n_arvores, 0)}</td>
                      <td>{fmtVol(s.volume_autorizado_m3)}</td>
                      <td>{fmtVol(s.volume_explorado_m3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {species.length > 12 && <p className="muted small">e mais {species.length - 12} espécies. Volumes em m³.</p>}
            </section>
          )}

          {d.parametros_volume.length > 0 && (
            <section>
              <h2>Parâmetros da estimativa de volume</h2>
              <dl className="params">
                {d.parametros_volume.map((pv) => (
                  <div key={pv.nome}>
                    <dt>{pv.nome}</dt>
                    <dd>
                      <b>
                        {fmt(pv.valor)} {pv.unidade ?? ""}
                      </b>
                      <small>
                        {pv.distribuicao} · {pv.origem}
                      </small>
                    </dd>
                  </div>
                ))}
              </dl>
              {Object.keys(d.modelo).length > 0 && (
                <p className="muted small">
                  Modelos:{" "}
                  {Object.entries(d.modelo)
                    .map(([k, v]) => `${k} ${v}`)
                    .join(" · ")}
                </p>
              )}
            </section>
          )}

          <section>
            <h2>Limitações</h2>
            {d.limitacoes.length ? (
              <ul className="limits">
                {d.limitacoes.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">Nenhuma limitação registrada pelo pipeline.</p>
            )}
          </section>

          <section>
            <h2>Proveniência</h2>
            <ul className="prov">
              {d.proveniencia.map((pv) => (
                <li key={pv.id}>
                  {/^https?:\/\//.test(pv.url) ? (
                    <a href={pv.url} target="_blank" rel="noreferrer">
                      {pv.fonte} <Icon name="external" size={13} />
                    </a>
                  ) : (
                    <span>{pv.fonte}</span>
                  )}
                  <small>
                    consultado em {fmtDate(pv.consultado_em)}
                    {pv.versao ? ` · versão ${pv.versao}` : ""}
                    {pv.licenca ? ` · ${pv.licenca}` : ""}
                  </small>
                </li>
              ))}
            </ul>
            <p className="aviso">{d.aviso}</p>
          </section>
        </aside>
      </div>
    </main>
  );
}
