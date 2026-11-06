import { useState } from "react";
import type { MetricaModelo, MetricsCalibracao, MetricsDetector } from "./types";
import { fmt, pct, staticMode, useData } from "./data";
import { CalibrationChart, CoverageBar } from "./Charts";
import { ErrorState, Icon, Loading, SimBadge } from "./ui";

type Strat = Record<string, Partial<MetricaModelo>>;

/** O pipeline real embute métricas por estrato como JSON dentro de `obs`; separa texto e dados. */
function splitObs(obs: string | null): { text: string; strata: Strat | null } {
  if (!obs) return { text: "", strata: null };
  const at = obs.indexOf("{");
  if (at < 0) return { text: obs, strata: null };
  let depth = 0;
  for (let i = at; i < obs.length; i++) {
    if (obs[i] === "{") depth++;
    else if (obs[i] === "}" && --depth === 0) {
      try {
        const strata = JSON.parse(obs.slice(at, i + 1)) as Strat;
        const before = obs.slice(0, at).replace(/Por tipo[^:]*:\s*$/i, "").trim();
        const after = obs.slice(i + 1).replace(/^[;.\s]+/, "").trim();
        return { text: [before, after].filter(Boolean).join(" "), strata };
      } catch {
        return { text: obs, strata: null };
      }
    }
  }
  return { text: obs, strata: null };
}

const stratumLabel: Record<string, string> = {
  corte_raso: "Corte raso",
  seletivo_degradacao: "Corte seletivo / degradação",
};

function Matrix({ m }: { m: number[][] }) {
  const total = m.flat().reduce((a, b) => a + b, 0) || 1;
  const labels = ["Sem distúrbio", "Distúrbio"];
  const cell = (i: number, j: number) => {
    const v = m[i]?.[j] ?? 0;
    const rowT = (m[i] ?? []).reduce((a, b) => a + b, 0) || 1;
    const kind = i === j ? "ok" : i === 0 ? "fp" : "fn";
    const name = i === j ? (i === 1 ? "acerto · distúrbio" : "acerto · floresta") : i === 0 ? "falso alarme" : "distúrbio perdido";
    return (
      <td key={j} className={`mx ${kind}`} style={{ "--a": (v / rowT).toFixed(3) } as React.CSSProperties}>
        <b>{fmt(v, 0)}</b>
        <span>
          {name} · {pct(v / rowT)} da linha
        </span>
      </td>
    );
  };
  return (
    <table className="matrix">
      <thead>
        <tr>
          <th />
          {labels.map((l) => (
            <th key={l}>Previsto: {l.toLowerCase()}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {m.slice(0, 2).map((_, i) => (
          <tr key={i}>
            <th scope="row">Referência: {labels[i].toLowerCase()}</th>
            {[0, 1].map((j) => cell(i, j))}
          </tr>
        ))}
      </tbody>
      <caption>{fmt(total, 0)} pixels de teste fora da amostra de treino</caption>
    </table>
  );
}

function Detector({ d }: { d: MetricsDetector }) {
  const [sel, setSel] = useState(d.selecionado);
  const model = d.modelos.find((m) => m.nome === sel) ?? d.modelos[0];
  const { text, strata } = splitObs(model?.obs ?? null);
  const best = (k: "iou" | "f1" | "precisao" | "recall") => Math.max(...d.modelos.map((m) => m[k] ?? -1));
  return (
    <section className="rel-card">
      <header>
        <h2>Detector de distúrbio florestal</h2>
        <p>Classifica cada pixel Sentinel-2 entre floresta estável e distúrbio (corte raso, corte seletivo, degradação) entre as datas antes e depois.</p>
      </header>
      <div className="protocol">
        <span>Protocolo</span>
        <p>{d.protocolo}</p>
        <span>Rótulos de referência</span>
        <p>{d.rotulos}</p>
      </div>
      <table className="models">
        <thead>
          <tr>
            <th>Modelo</th>
            <th>IoU</th>
            <th>F1</th>
            <th>Precisão</th>
            <th>Recall</th>
          </tr>
        </thead>
        <tbody>
          {d.modelos.map((m) => (
            <tr key={m.nome} className={m.nome === model?.nome ? "on" : ""} onClick={() => setSel(m.nome)}>
              <td>
                <button type="button" className="radio" aria-pressed={m.nome === model?.nome} onClick={() => setSel(m.nome)}>
                  <i />
                  {m.nome}
                </button>
                {m.nome === d.selecionado && <span className="tag">em uso</span>}
              </td>
              {(["iou", "f1", "precisao", "recall"] as const).map((k) => (
                <td key={k} className={m[k] != null && m[k] === best(k) && d.modelos.length > 1 ? "best" : ""}>
                  {pct(m[k])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">Clique em um modelo para ver a matriz de confusão. Negrito: melhor valor da coluna.</p>
      <h3>Matriz de confusão · {model?.nome}</h3>
      {model?.matriz_confusao ? <Matrix m={model.matriz_confusao} /> : <p className="muted">Matriz não avaliada para este modelo.</p>}
      {strata && (
        <>
          <h3>Desempenho por tipo de distúrbio · {model?.nome}</h3>
          <table className="models compact">
            <thead>
              <tr>
                <th>Estrato</th>
                <th>IoU</th>
                <th>F1</th>
                <th>Precisão</th>
                <th>Recall</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(strata).map(([k, v]) => (
                <tr key={k}>
                  <td>{stratumLabel[k] ?? k.replaceAll("_", " ")}</td>
                  <td>{pct(v.iou)}</td>
                  <td>{pct(v.f1)}</td>
                  <td>{pct(v.precisao)}</td>
                  <td>{pct(v.recall)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {text && (
        <div className="obs">
          <Icon name="info" size={15} />
          <p>{text}</p>
        </div>
      )}
    </section>
  );
}

function Calibration({ c }: { c: MetricsCalibracao }) {
  const cov = c.cobertura_p10_p90;
  const diff = cov != null ? cov - c.cobertura_nominal : null;
  const verdict =
    diff == null
      ? null
      : Math.abs(diff) <= 0.05
        ? "As faixas estão bem calibradas: a largura declarada corresponde ao que se observa."
        : diff < 0
          ? "As faixas estão um pouco estreitas: a incerteza real é maior do que a indicada. Por isso os indícios usam p90 como limite, e não a mediana."
          : "As faixas estão conservadoras (mais largas que o necessário): os indícios tendem a ser subestimados.";
  return (
    <section className="rel-card">
      <header>
        <h2>Calibração do volume</h2>
        <p>Converte a fração de cada célula de 1 ha com distúrbio detectado em volume de madeira compatível (m³/ha), aprendido com UPAs cujas árvores exploradas foram declaradas no IF100.</p>
      </header>
      <div className="protocol">
        <span>Protocolo</span>
        <p>{c.protocolo}</p>
      </div>
      <CalibrationChart data={c} />
      <dl className="kpis">
        <div>
          <dt>R²</dt>
          <dd>{c.r2 != null ? c.r2.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}</dd>
        </div>
        <div>
          <dt>Erro médio absoluto</dt>
          <dd>
            {fmt(c.mae_m3_ha)} <small>m³/ha</small>
          </dd>
        </div>
        <div>
          <dt>UPAs de treino</dt>
          <dd>{fmt(c.n_upas, 0)}</dd>
        </div>
        <div>
          <dt>Células</dt>
          <dd>{fmt(c.n_celulas_treino, 0)}</dd>
        </div>
      </dl>
      <div className="coverage">
        <div className="cov-num">
          <b>{pct(cov)}</b>
          <span>cobertura empírica p10–p90</span>
        </div>
        <div className="cov-body">
          <CoverageBar value={cov} nominal={c.cobertura_nominal} />
          <p>
            Em teoria, o volume real deveria cair dentro da faixa p10–p90 em <b>{pct(c.cobertura_nominal)}</b> das células. Testando em UPAs que o modelo não viu, isso aconteceu em <b>{pct(cov)}</b>.{" "}
            {verdict}
          </p>
        </div>
      </div>
      {c.obs && (
        <div className="obs">
          <Icon name="info" size={15} />
          <p>{c.obs}</p>
        </div>
      )}
    </section>
  );
}

export function Reliability() {
  const det = useData<MetricsDetector>("/metrics/detector");
  const cal = useData<MetricsCalibracao>("/metrics/calibracao");
  const simulated = staticMode || [det.data?.modelos.map((m) => m.obs).join(" "), cal.data?.obs].some((s) => /\bmock\b/i.test(s ?? ""));
  return (
    <main className="reliability">
      <div className="page-head">
        <div>
          <h1>Confiabilidade</h1>
          <p>Quanto confiar no detector de distúrbio e na estimativa de volume, medido em áreas que os modelos não viram no treino.</p>
        </div>
        <SimBadge show={simulated} />
      </div>
      <div className="rel-grid">
        {det.data ? (
          <Detector d={det.data} />
        ) : det.error ? (
          <ErrorState title="Métricas do detector indisponíveis" message={det.error} retry={det.retry} />
        ) : (
          <Loading label="Carregando métricas do detector…" />
        )}
        {cal.data ? (
          <Calibration c={cal.data} />
        ) : cal.error ? (
          <ErrorState title="Calibração ainda não publicada" message={cal.notFound ? "O pipeline ainda não gerou metrics/calibracao.json neste acervo." : cal.error} retry={cal.retry} />
        ) : (
          <Loading label="Carregando calibração…" />
        )}
      </div>
      <div className="rel-text">
        <section>
          <h2>Como ler estes números</h2>
          <dl className="glossary">
            <div>
              <dt>Precisão</dt>
              <dd>Dos pixels que o detector marcou como distúrbio, quantos realmente eram. Precisão baixa significa mais falsos alarmes.</dd>
            </div>
            <div>
              <dt>Recall</dt>
              <dd>Dos distúrbios de referência, quantos o detector encontrou. Recall baixo significa clareiras perdidas, o que tende a gerar indício de volume sem lastro.</dd>
            </div>
            <div>
              <dt>IoU e F1</dt>
              <dd>Resumem precisão e recall num número só. IoU acima de 50% já é útil para triagem em escala de célula de 1 ha.</dd>
            </div>
            <div>
              <dt>Faixa p10–p90</dt>
              <dd>Intervalo em que o volume real deve estar 8 a cada 10 vezes. Um indício só é aberto quando o declarado supera o p90.</dd>
            </div>
          </dl>
        </section>
        <section>
          <h2>Limites conhecidos</h2>
          <ul className="limits">
            <li>Clareiras de árvore isolada (200–600 m²) ficam abaixo da resolução de 10 m e se fecham em meses; por isso o volume é avaliado por célula, nunca por árvore.</li>
            <li>DETER e PRODES são rótulos de referência imperfeitos: não captam todas as pequenas clareiras de manejo.</li>
            <li>Nuvens e sombra deixam células sem observação; elas aparecem hachuradas e não geram indício.</li>
            <li>Validação espacial em blocos evita que vizinhos do treino inflem os números, mas o desempenho pode variar fora do polo AMACRO.</li>
            <li>Todo resultado é indício para priorizar fiscalização; a conclusão exige vistoria e análise técnica.</li>
          </ul>
        </section>
      </div>
    </main>
  );
}
