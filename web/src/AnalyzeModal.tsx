import { useEffect, useRef, useState } from "react";
import { initialize, staticMode } from "./data";
import { Icon } from "./ui";

type Job = {
  job_id?: string;
  status: "queued" | "running" | "done" | "error" | string;
  etapa?: string;
  progresso?: number;
  mensagem?: string;
  cached?: boolean;
  resultado?: { autex?: string } | null;
};

const STEPS = ["Carregando autorização e árvores declaradas", "Baixando imagens e detectando distúrbio", "Estimando volume e aplicando regras", "Gerando dossiê"];

export function AnalyzeModal({ close, initial = "" }: { close: () => void; initial?: string }) {
  const [autex, setAutex] = useState(initial);
  const [job, setJob] = useState<Job>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    const d = dialog.current;
    if (d && !d.open) d.showModal();
    return () => {
      alive.current = false;
    };
  }, []);

  async function submit() {
    const id = autex.trim();
    if (!id) return;
    setError("");
    setJob(undefined);
    setBusy(true);
    try {
      await initialize();
      if (staticMode) throw Error("A análise sob demanda precisa da API local em execução. No modo de demonstração estático, os dossiês já processados continuam disponíveis.");
      if (!/^[A-Za-z0-9_-]+$/.test(id)) throw Error("Use apenas letras, números, hífen ou sublinhado no número AUTEX.");
      const r = await fetch(`/api/analyze/${encodeURIComponent(id)}`, { method: "POST" });
      const started = (await r.json().catch(() => ({}))) as Job & { detail?: unknown };
      if (!r.ok) throw Error(typeof started.detail === "string" ? started.detail : "Não foi possível iniciar a análise.");
      let cur: Job = started;
      const jobId = started.job_id;
      for (let i = 0; i < 400 && alive.current; i++) {
        setJob(cur);
        if (cur.status === "done") {
          await new Promise((res) => setTimeout(res, cur.cached ? 650 : 350));
          if (!alive.current) return;
          location.hash = `/caso/${encodeURIComponent(cur.resultado?.autex ?? id)}`;
          close();
          return;
        }
        if (cur.status === "error")
          throw Error(
            `Não foi possível analisar a autorização ${id} agora. Confira o número AUTEX ou tente mais tarde; os dossiês já processados seguem disponíveis na triagem.${cur.mensagem ? ` (${cur.mensagem})` : ""}`,
          );
        if (!jobId) throw Error("A API não retornou o identificador da análise.");
        await new Promise((res) => setTimeout(res, 1000));
        if (!alive.current) return;
        const jr = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
        if (!jr.ok) throw Error("O acompanhamento da análise foi interrompido. Tente novamente.");
        cur = (await jr.json()) as Job;
      }
      if (alive.current) throw Error("A análise segue em execução. Tente abrir o dossiê novamente em alguns minutos.");
    } catch (e) {
      if (alive.current) setError(e instanceof Error ? e.message : "Erro inesperado.");
    } finally {
      if (alive.current) setBusy(false);
    }
  }

  const p = Math.max(0, Math.min(1, job?.progresso ?? 0));
  const stepIdx = job?.status === "done" ? STEPS.length : Math.min(STEPS.length - 1, Math.floor(p * STEPS.length));

  return (
    <dialog ref={dialog} className="modal" onCancel={close} onClick={(e) => e.target === dialog.current && !busy && close()} aria-labelledby="an-title">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="modal-head">
          <div>
            <h2 id="an-title">Analisar autorização</h2>
            <p>Cruza a declaração IF100, os limites autorizados no Sinaflor e as imagens Sentinel-2 da área.</p>
          </div>
          <button type="button" className="icon-btn" onClick={close} aria-label="Fechar">
            <Icon name="close" size={18} />
          </button>
        </div>
        <label className="field">
          <span>Número AUTEX</span>
          <input
            autoFocus
            className="mono"
            value={autex}
            onChange={(e) => setAutex(e.target.value)}
            placeholder="ex.: 1234567"
            disabled={busy}
            spellCheck={false}
            autoComplete="off"
          />
          <small>Autorizações já processadas abrem direto do acervo; as demais são analisadas na hora (até 90 s).</small>
        </label>

        {job && !error && (
          <div className="progress-block" aria-live="polite">
            <div className="progress-head">
              <b>{job.status === "done" ? (job.cached ? "Encontrado no acervo processado" : "Análise concluída") : job.etapa ?? "Na fila"}</b>
              <span>{Math.round((job.status === "done" ? 1 : p) * 100)}%</span>
            </div>
            <div className="progress-track">
              <span style={{ width: `${(job.status === "done" ? 1 : Math.max(0.03, p)) * 100}%` }} />
            </div>
            <ol className="steps">
              {STEPS.map((s, i) => (
                <li key={s} className={i < stepIdx ? "done" : i === stepIdx ? "now" : ""}>
                  {i < stepIdx ? <Icon name="check" size={14} /> : <i />}
                  {s}
                </li>
              ))}
            </ol>
          </div>
        )}

        {error && (
          <div className="form-error" role="alert">
            <Icon name="alert" size={16} />
            <span>{error}</span>
          </div>
        )}

        <div className="modal-actions">
          <button type="button" className="ghost" onClick={close}>
            {busy ? "Fechar e continuar depois" : "Cancelar"}
          </button>
          <button className="primary" disabled={busy || !autex.trim()}>
            {busy ? "Analisando…" : "Iniciar análise"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
