import { useEffect, useRef, useState } from "react";
import { staticMode, initialize } from "./data";
type Job = {
  id?: string;
  job_id?: string;
  status: string;
  progress?: number;
  progresso?: number;
  stage?: string;
  etapa?: string;
  error?: string;
  erro?: string;
  mensagem?: string;
  autex?: string;
};
export function AnalyzeModal({ close }: { close: () => void }) {
  const [autex, setAutex] = useState("");
  const [job, setJob] = useState<Job>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    dialog.current?.showModal();
    return () => {
      active.current = false;
    };
  }, []);
  async function submit() {
    setError("");
    setBusy(true);
    try {
      await initialize();
      if (staticMode)
        throw Error(
          "A análise precisa da API local em execução. O modo estático permite consultar os dossiês simulados.",
        );
      const response = await fetch(
        `/api/analyze/${encodeURIComponent(autex.trim())}`,
        { method: "POST" },
      );
      const started = await response.json();
      if (!response.ok)
        throw Error(
          typeof started.detail === "string"
            ? started.detail
            : "Não foi possível iniciar a análise.",
        );
      let current: Job = started;
      const id = current.id ?? current.job_id;
      if (!id) throw Error("A API não retornou o identificador da análise.");
      for (let attempt = 0; attempt < 600 && active.current; attempt++) {
        setJob(current);
        if (
          ["completed", "done", "concluido", "success"].includes(current.status)
        ) {
          location.hash = `/caso/${encodeURIComponent(current.autex ?? autex.trim())}`;
          close();
          return;
        }
        if (["failed", "error", "erro"].includes(current.status))
          throw Error(
            current.error ??
              current.erro ??
              current.mensagem ??
              "A análise não pôde ser concluída.",
          );
        await new Promise((r) => setTimeout(r, 1500));
        if (!active.current) return;
        const r = await fetch(`/api/jobs/${encodeURIComponent(id)}`);
        if (!r.ok) throw Error("Acompanhamento interrompido. Tente novamente.");
        current = await r.json();
      }
      if (active.current)
        throw Error(
          "A análise ainda está em execução. Consulte novamente mais tarde.",
        );
    } catch (e) {
      if (active.current)
        setError(e instanceof Error ? e.message : "Erro inesperado.");
    } finally {
      if (active.current) setBusy(false);
    }
  }
  const progress = job?.progress ?? job?.progresso ?? 0;
  return (
    <dialog ref={dialog} onCancel={close}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="title-row">
          <h2>Analisar autorização</h2>
          <button type="button" onClick={close} aria-label="Fechar">
            ×
          </button>
        </div>
        <p>Cruzar declaração, limites autorizados e observações de satélite.</p>
        <label className="field">
          Número AUTEX
          <input
            autoFocus
            required
            value={autex}
            onChange={(e) => setAutex(e.target.value)}
            placeholder="Informe o número da autorização"
            disabled={busy}
          />
        </label>
        {job && (
          <div aria-live="polite">
            <progress
              max="100"
              value={progress <= 1 ? progress * 100 : progress}
            />
            <p>{job.stage ?? job.etapa ?? "Processando autorização…"}</p>
          </div>
        )}
        {error && (
          <p className="warning" role="alert">
            {error}
          </p>
        )}
        <button className="primary" disabled={busy || !autex.trim()}>
          {busy ? "Análise em andamento…" : "Iniciar análise"}
        </button>
      </form>
    </dialog>
  );
}
