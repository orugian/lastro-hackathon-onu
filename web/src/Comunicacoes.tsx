import { useState } from "react";
import { fmtDate, staticMode, titleCase, useData } from "./data";
import { ErrorState, Icon, Loading, SimBadge } from "./ui";

type Evento = { em: string; acao: string; por: string; detalhe: string };
type Comunicacao = {
  protocolo: string; autex: string; score: number; tipo: string; municipio: string; uf: string;
  indicios: string[]; source_mode: string; status: string; sha256: string; criado_em: string;
  enviado_em?: string; canal?: string; trilha: Evento[];
};
type Fila = {
  limiar: number; conector: string; confirmacao_humana: boolean; aviso: string;
  destino: { orgao: string; canal: string; assunto: string };
  ultima_varredura: { novos: number; total: number }; comunicacoes: Comunicacao[];
};

const STATUS: Record<string, [string, string]> = {
  aguardando_confirmacao: ["Aguardando confirmação", "st-wait"],
  pronto_para_envio: ["Pronto para envio", "st-wait"],
  enviado_simulado: ["Enviado (demonstração)", "st-ok"],
  enviado: ["Enviado", "st-ok"],
  pronto_falabr: ["Pronto para protocolo Fala.BR", "st-ok"],
  bloqueado_simulacao: ["Bloqueado · cenário simulado", "st-off"],
  descartado: ["Descartado pelo servidor", "st-off"],
  erro_envio: ["Erro no envio", "st-err"],
};
const ACAO: Record<string, string> = {
  gerado_automaticamente: "Gerado automaticamente", confirmado: "Confirmado", enviado: "Enviado",
  envio_bloqueado: "Envio bloqueado", descartado: "Descartado", erro_envio: "Erro no envio",
};
const CONECTOR: Record<string, string> = {
  simulado: "caixa de saída local (demonstração, sem contato externo)",
  email: "e-mail institucional (SMTP)",
  falabr: "texto para protocolo no Fala.BR",
};

function Acao({ c, done }: { c: Comunicacao; done: () => void }) {
  const [open, setOpen] = useState<"confirmar" | "descartar" | null>(null);
  const [servidor, setServidor] = useState("");
  const [just, setJust] = useState("");
  const [err, setErr] = useState("");
  const pend = ["aguardando_confirmacao", "pronto_para_envio", "erro_envio"].includes(c.status);
  if (!pend) return null;
  const send = async () => {
    setErr("");
    const r = await fetch(`/api/comunicacoes/${c.protocolo}/${open}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ servidor, justificativa: just }),
    });
    if (!r.ok) return setErr((await r.json().catch(() => ({}))).detail ?? "Falha ao registrar.");
    setOpen(null);
    done();
  };
  if (!open)
    return (
      <div className="com-actions">
        <button type="button" className="primary" onClick={() => setOpen("confirmar")}>
          <Icon name="check" size={15} /> Revisar e enviar
        </button>
        <button type="button" onClick={() => setOpen("descartar")}>Descartar</button>
      </div>
    );
  return (
    <div className="com-confirm">
      <p>
        {open === "confirmar"
          ? "Confirme que revisou o dossiê e que o indício justifica comunicar o órgão. A confirmação fica registrada na trilha de auditoria."
          : "Registre por que esta comunicação não deve seguir."}
      </p>
      <input placeholder="Servidor responsável (nome e matrícula)" value={servidor} onChange={(e) => setServidor(e.target.value)} />
      <textarea placeholder="Justificativa (mín. 10 caracteres)" value={just} onChange={(e) => setJust(e.target.value)} rows={2} />
      {err && <p className="form-error">{err}</p>}
      <div className="com-actions">
        <button type="button" className="primary" onClick={send}>{open === "confirmar" ? "Confirmar envio" : "Confirmar descarte"}</button>
        <button type="button" onClick={() => setOpen(null)}>Cancelar</button>
      </div>
    </div>
  );
}

export function Comunicacoes() {
  const { data, error, retry } = useData<Fila>(staticMode ? null : "/comunicacoes");
  if (staticMode) return <ErrorState title="Indisponível no modo estático" message="A fila de comunicações exige a API local em execução." />;
  if (!data) return error ? <ErrorState message={error} retry={retry} /> : <Loading label="Varrendo casos acima do limiar…" />;
  const pend = data.comunicacoes.filter((c) => ["aguardando_confirmacao", "pronto_para_envio"].includes(c.status)).length;
  return (
    <main className="com-page">
      <div className="com-head">
        <div>
          <h1>Comunicações ao IBAMA</h1>
          <p className="com-sub">
            Regra automática: casos com <b>prioridade ≥ {Math.round(data.limiar * 100)}</b> e ao menos um indício geram um protocolo
            com dossiê, evidências, AUTEX/DOF e hash SHA-256, destinado a <b>{data.destino.orgao}</b>.
          </p>
        </div>
        <div className="com-kpis">
          <span><b>{data.comunicacoes.length}</b> protocolos</span>
          <span><b>{pend}</b> aguardando revisão</span>
        </div>
      </div>
      <div className="com-rule">
        <Icon name="info" size={16} />
        <p>
          Envio por <b>{CONECTOR[data.conector] ?? data.conector}</b>.{" "}
          {data.confirmacao_humana
            ? "Cada envio exige confirmação de um servidor identificado (salvaguarda): o score é índice de prioridade, não probabilidade de irregularidade."
            : "Envio automático sem confirmação humana está ATIVO."}{" "}
          Canal oficial: {data.destino.canal}. Cenários simulados nunca são enviados.
        </p>
      </div>
      {data.comunicacoes.length === 0 ? (
        <div className="state"><p>Nenhum caso acima do limiar.</p></div>
      ) : (
        <ul className="com-list">
          {data.comunicacoes.map((c) => {
            const [lbl, cls] = STATUS[c.status] ?? [c.status, ""];
            return (
              <li key={c.protocolo} className="com-item">
                <div className="com-top">
                  <div>
                    <div className="com-id">
                      <span className="mono">{c.protocolo}</span>
                      <span className={`com-status ${cls}`}>{lbl}</span>
                      <SimBadge show={c.source_mode === "simulado"} />
                    </div>
                    <div className="com-case">
                      AUTEX <a href={`#/caso/${encodeURIComponent(c.autex)}`} className="mono">{c.autex}</a> · {c.tipo} · {titleCase(c.municipio)}/{c.uf}
                      {" · indícios "}{c.indicios.map((f) => <span key={f} className="flagchip">{f}</span>)}
                    </div>
                  </div>
                  <div className="com-score"><b>{Math.round(c.score * 100)}</b><small>prioridade</small></div>
                </div>
                <div className="com-meta">
                  <a href={`/api/comunicacoes/${c.protocolo}/texto`} target="_blank" rel="noreferrer"><Icon name="doc" size={14} /> Texto da comunicação</a>
                  <a href={`/api/cases/${encodeURIComponent(c.autex)}/dossier.html`} target="_blank" rel="noreferrer"><Icon name="print" size={14} /> Dossiê anexo</a>
                  <span className="mono hash" title={c.sha256}>SHA-256 {c.sha256.slice(0, 16)}…</span>
                </div>
                <ol className="com-trail">
                  {c.trilha.map((e, i) => (
                    <li key={i}><b>{ACAO[e.acao] ?? e.acao}</b> · {fmtDate(e.em)} {e.em.slice(11, 16)} UTC · {e.por}{e.detalhe ? ` — ${e.detalhe}` : ""}</li>
                  ))}
                </ol>
                <Acao c={c} done={retry} />
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
