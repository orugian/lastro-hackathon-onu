import { useEffect, useState } from "react";
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

const METRICS = ["iou", "f1", "precisao", "recall"] as const;
const isColab = (m: MetricaModelo) => /^\[colab\]/i.test(m.nome);
const isLocal5 = (m: MetricaModelo) => /^\[local 5 km\]/i.test(m.nome);
const shortName = (n: string) => n.replace(/^\[(colab|local 5 km)\]\s*/i, "");

function ModelTable({ models, selected, inUse, onSelect }: { models: MetricaModelo[]; selected?: string; inUse?: string; onSelect: (n: string) => void }) {
  const best = (k: (typeof METRICS)[number]) => Math.max(...models.map((m) => m[k] ?? -1));
  return (
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
        {models.map((m) => (
          <tr key={m.nome} className={m.nome === selected ? "on" : ""} onClick={() => onSelect(m.nome)}>
            <td>
              <button type="button" className="radio" aria-pressed={m.nome === selected} onClick={() => onSelect(m.nome)}>
                <i />
                {shortName(m.nome)}
              </button>
              {m.nome === inUse && <span className="tag">em uso</span>}
            </td>
            {METRICS.map((k) => (
              <td key={k} className={m[k] != null && m[k] === best(k) && models.length > 1 ? "best" : ""}>
                {pct(m[k], 1)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Strata({ strata, name }: { strata: Strat; name?: string }) {
  return (
    <>
      <h3>Desempenho por tipo de distúrbio · {name}</h3>
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
  );
}

function HeadToHead({ models, inUse }: { models: MetricaModelo[]; inUse: string }) {
  const [sel, setSel] = useState(inUse);
  const model = models.find((m) => m.nome === sel) ?? models[0];
  const emUso = models.find((m) => m.nome === inUse);
  const unet = models.find((m) => /u-?net siamesa$/i.test(m.nome));
  const lgbm = models.find((m) => /\] lightgbm$/i.test(m.nome));
  const { text } = splitObs(model?.obs ?? null);
  const f3 = (v: number | null) => (v == null ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 }));
  const fa = (m?: MetricaModelo) => (m?.matriz_confusao ? m.matriz_confusao[0][1] / Math.max(1, m.matriz_confusao[0][0] + m.matriz_confusao[0][1]) : null);
  if (!models.length) return null;
  return (
    <>
      <div className="group-title">
        <h3>Validação independente · blocos de 5 km nunca vistos pela U-Net</h3>
        <span>decide o detector em uso</span>
      </div>
      {emUso && lgbm && unet && fa(emUso) != null && fa(lgbm) != null && (
        <div className="dl-highlight">
          <div className="dl-vs">
            <div>
              <b>{pct(fa(emUso), 1)}</b>
              <span>falso alarme · LightGBM + U-Net</span>
            </div>
            <i aria-hidden="true">vs</i>
            <div className="dim">
              <b>{pct(fa(lgbm), 1)}</b>
              <span>falso alarme · LightGBM sozinho</span>
            </div>
          </div>
          <p>
            A U-Net (deep learning) entra como <b>segunda opinião</b>: só conta como distúrbio o pixel que o LightGBM e a U-Net marcam juntos. Em{" "}
            {fmt(emUso.n_pixels_teste, 0)} pixels de blocos que nenhum dos dois viu, isso corta o falso alarme de {pct(fa(lgbm), 1)} para {pct(fa(emUso), 1)},
            com precisão {pct(emUso.precisao)} e IoU equivalente ({f3(emUso.iou)} × {f3(lgbm.iou)}). Sozinha, a U-Net acerta mais área (IoU {f3(unet.iou)}), mas
            marca floresta intacta demais ({pct(fa(unet), 1)}); como casos acima do limiar geram comunicação ao IBAMA, a operação prioriza precisão.
          </p>
        </div>
      )}
      <ModelTable models={models} selected={model?.nome} inUse={inUse} onSelect={setSel} />
      {model?.matriz_confusao && (
        <>
          <h3>Matriz de confusão · {shortName(model.nome)}</h3>
          <Matrix m={model.matriz_confusao} />
        </>
      )}
      {text && (
        <div className="obs">
          <Icon name="info" size={15} />
          <p>{text}</p>
        </div>
      )}
    </>
  );
}

function Detector({ d }: { d: MetricsDetector }) {
  const local = d.modelos.filter((m) => !isColab(m) && !isLocal5(m));
  const local5 = d.modelos.filter(isLocal5);
  const [sel, setSel] = useState(local.find((m) => /lightgbm/i.test(m.nome))?.nome ?? local[0]?.nome);
  const model = local.find((m) => m.nome === sel) ?? local[0];
  const { text, strata } = splitObs(model?.obs ?? null);
  const [protoLocal] = d.protocolo.split(" | ");
  return (
    <section className="rel-card">
      <header>
        <h2>Detector de distúrbio florestal</h2>
        <p>Classifica cada pixel Sentinel-2 entre floresta estável e distúrbio (corte raso, corte seletivo, degradação) entre as datas antes e depois.</p>
      </header>
      <HeadToHead models={local5} inUse={d.selecionado} />
      <div className="group-title">
        <h3>Treino local · GroupKFold espacial (5 km)</h3>
        <span>LightGBM × baseline; alimenta a calibração de volume</span>
      </div>
      <div className="protocol">
        <span>Protocolo</span>
        <p>{protoLocal}</p>
        <span>Rótulos de referência</span>
        <p>{d.rotulos}</p>
      </div>
      {local.length ? (
        <ModelTable models={local} selected={model?.nome} inUse="lightgbm" onSelect={setSel} />
      ) : (
        <p className="muted">Nenhum modelo avaliado neste protocolo.</p>
      )}
      <p className="muted small">Clique em um modelo para ver a matriz de confusão. Negrito: melhor valor da coluna. Compare apenas modelos do mesmo grupo.</p>
      {model && (
        <>
          <h3>Matriz de confusão · {shortName(model.nome)}</h3>
          {model.matriz_confusao ? <Matrix m={model.matriz_confusao} /> : <p className="muted">Matriz não avaliada para este modelo.</p>}
        </>
      )}
      {strata && <Strata strata={strata} name={model?.nome} />}
      {text && (
        <div className="obs">
          <Icon name="info" size={15} />
          <p>{text}</p>
        </div>
      )}
    </section>
  );
}

type DlJson = {
  metricas?: { protocolo?: string; obs?: string[] | string };
  config?: { gpu?: string; epocas_executadas?: number; n_chips?: number; chip_px?: number; bloco_m?: number; treino?: { epoch: number; train: number; val: number }[] };
};

function useDl() {
  const [dl, setDl] = useState<DlJson | null>(null);
  useEffect(() => {
    let on = true;
    (async () => {
      for (const u of ["/api/metrics/dl", "/dl/dl.json"]) {
        try {
          const r = await fetch(u);
          if (r.ok && (r.headers.get("content-type") ?? "").includes("json")) {
            const j = (await r.json()) as DlJson;
            if (on) setDl(j);
            return;
          }
        } catch {
          /* tenta a próxima fonte */
        }
      }
    })();
    return () => {
      on = false;
    };
  }, []);
  return dl;
}

function LossChart({ pts }: { pts: { epoch: number; train: number; val: number }[] }) {
  const W = 620,
    H = 210,
    L = 36,
    R = 10,
    T = 12,
    B = 30;
  const maxE = Math.max(...pts.map((p) => p.epoch));
  const minE = Math.min(...pts.map((p) => p.epoch));
  const maxY = Math.ceil(Math.max(...pts.flatMap((p) => [p.train, p.val])) * 10) / 10;
  const x = (e: number) => L + ((e - minE) / Math.max(1, maxE - minE)) * (W - L - R);
  const y = (v: number) => T + (1 - v / maxY) * (H - T - B);
  const line = (k: "train" | "val") => pts.map((p, i) => `${i ? "L" : "M"}${x(p.epoch).toFixed(1)},${y(p[k]).toFixed(1)}`).join(" ");
  const bestVal = pts.reduce((a, b) => (b.val < a.val ? b : a));
  return (
    <svg className="losschart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Curva de perda por época, treino e validação">
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line x1={L} x2={W - R} y1={y(maxY * f)} y2={y(maxY * f)} stroke="#e4e8dc" />
          <text x={L - 6} y={y(maxY * f) + 4} textAnchor="end" className="axis">
            {(maxY * f).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}
          </text>
        </g>
      ))}
      {pts.map((p) => (
        <text key={p.epoch} x={x(p.epoch)} y={H - 12} textAnchor="middle" className="axis">
          {p.epoch}
        </text>
      ))}
      <path d={line("train")} fill="none" stroke="#9db58f" strokeWidth={2} strokeDasharray="5 3" />
      <path d={line("val")} fill="none" stroke="#173a2c" strokeWidth={2.5} />
      <circle cx={x(bestVal.epoch)} cy={y(bestVal.val)} r={4.5} fill="#c5f67c" stroke="#173a2c" strokeWidth={2} />
      <text x={W - R} y={H} textAnchor="end" className="axis">
        época
      </text>
    </svg>
  );
}

function DeepLearning({ d }: { d: MetricsDetector }) {
  const colab = d.modelos.filter(isColab);
  const dl = useDl();
  const [sel, setSel] = useState(() => colab.reduce((a, b) => ((b.iou ?? 0) > (a.iou ?? 0) ? b : a), colab[0])?.nome);
  const [ex, setEx] = useState(1);
  if (!colab.length) return null;
  const model = colab.find((m) => m.nome === sel) ?? colab[0];
  const unet = colab.find((m) => /u-?net/i.test(m.nome));
  const lgbm = colab.find((m) => /lightgbm/i.test(m.nome));
  const proto = d.protocolo.split(" | ")[1] ?? dl?.metricas?.protocolo ?? "";
  const cfg = dl?.config;
  const curve = cfg?.treino ?? [];
  const obsFirst = (model?.obs ?? "").split(/(?<=\.)\s/)[0];
  return (
    <section className="rel-card dl-card">
      <header className="dl-head">
        <div>
          <h2>Treino deep learning (Colab, GPU)</h2>
          <p>Segundo protocolo, independente: U-Net siamesa comparada ao LightGBM e a um baseline sem treino nos mesmos pixels de teste espacial (blocos de 25 km).</p>
        </div>
        <span className="exp-tag">treino da U-Net · em uso como confirmação</span>
      </header>
      {unet && lgbm && unet.iou != null && lgbm.iou != null && (
        <div className="dl-highlight">
          <div className="dl-vs">
            <div>
              <b>{unet.iou.toLocaleString("pt-BR", { maximumFractionDigits: 3, minimumFractionDigits: 3 })}</b>
              <span>IoU · {shortName(unet.nome)}</span>
            </div>
            <i aria-hidden="true">vs</i>
            <div className="dim">
              <b>{lgbm.iou.toLocaleString("pt-BR", { maximumFractionDigits: 3, minimumFractionDigits: 3 })}</b>
              <span>IoU · {shortName(lgbm.nome)}</span>
            </div>
          </div>
          <p>
            Nos <b>mesmos {fmt(unet.n_pixels_teste, 0)} pixels</b> de teste, a U-Net supera o LightGBM em IoU por {fmt((unet.iou - lgbm.iou) * 100)} pontos percentuais
            {unet.recall != null && lgbm.recall != null && <> e encontra mais distúrbio (recall {pct(unet.recall)} contra {pct(lgbm.recall)})</>}. Os pesos foram exportados para ONNX e rodam localmente na CPU (≈ 5 s por autorização), confirmando a detecção do LightGBM.
          </p>
        </div>
      )}
      <div className="dl-grid">
        <div className="dl-col">
          <div className="protocol">
            <span>Protocolo</span>
            <p>{proto}</p>
          </div>
          <ModelTable models={colab} selected={model?.nome} onSelect={setSel} />
          <p className="muted small">Números comparáveis apenas dentro deste grupo; o protocolo local usa outros pixels e blocos de 5 km.</p>
          {model?.matriz_confusao && (
            <>
              <h3>Matriz de confusão · {shortName(model.nome)}</h3>
              <Matrix m={model.matriz_confusao} />
            </>
          )}
        </div>
        <div className="dl-col">
          <figure className="dl-example">
            <img src={`/dl/dl_exemplo_${ex}.png`} alt={`Exemplo ${ex} do teste espacial: imagem pré, pós, rótulo de referência e probabilidade prevista pela U-Net`} loading="lazy" />
            <figcaption>
              <span>Exemplo do teste espacial: pré · pós · rótulo PRODES/DETER (branco = ignorado) · probabilidade prevista</span>
              <span className="pager">
                {[1, 2, 3, 4].map((i) => (
                  <button key={i} type="button" className={i === ex ? "on" : ""} aria-label={`Exemplo ${i}`} aria-pressed={i === ex} onClick={() => setEx(i)}>
                    {i}
                  </button>
                ))}
              </span>
            </figcaption>
          </figure>
          {curve.length > 1 && (
            <div className="loss">
              <div className="loss-head">
                <h3>Perda por época</h3>
                <span className="loss-key">
                  <i className="k-val" /> validação <i className="k-train" /> treino
                </span>
              </div>
              <LossChart pts={curve} />
              <p className="muted small">
                {cfg?.epocas_executadas ?? curve.length} épocas com parada antecipada · {fmt(cfg?.n_chips, 0)} chips de {cfg?.chip_px ?? "—"} px · GPU {cfg?.gpu ?? "—"}. Ponto lima: menor perda de validação.
              </p>
            </div>
          )}
          {obsFirst && (
            <div className="obs">
              <Icon name="info" size={15} />
              <p>Rótulos fracos e amostragem enriquecida em positivos: as métricas medem concordância com PRODES/DETER, não prevalência regional.</p>
            </div>
          )}
        </div>
      </div>
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
      {det.data && <DeepLearning d={det.data} />}
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
