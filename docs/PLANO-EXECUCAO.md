# Lastro — Plano de execução (8 h, multiagente)

> O volume de madeira declarado tem lastro na floresta?
> Triagem antifraude que cruza autorizações Sinaflor, árvores declaradas como exploradas (IF100), DOF e imagens de satélite (Sentinel-2 e CBERS-4A) para priorizar a fiscalização. Resultado experimental: não constitui prova nem auto de infração.

---

## 1. Decisões alinhadas (grill)

| # | Tema | Decisão |
|---|---|---|
| Q1 | Regime | Modelo híbrido. O caso principal é **POA/PMFS** (manejo seletivo), com volume por espécie e por árvore. O segundo caso é **ASV/UAS** (corte raso). |
| Q2 | Dados | **Autorizações reais** passam por triagem prévia. Um **cenário simulado de reserva**, marcado como SIMULAÇÃO, garante que todas as flags apareçam. |
| Q3 | Base de código | Projeto novo em `SOLUCAO-FINAL/`. Do RAIZTRACE reaproveitamos a identidade visual (DESIGN.md) e o padrão de cache com proveniência. |
| Q4 | Stack | Pipeline Python 3.11 (uv) que grava artefatos. Backend FastAPI. Front React + Vite + MapLibre. |
| Q5 | Detector | Núcleo: baseline espectral sem treino + **LightGBM** com rótulos PRODES/DETER. Trilha DL (Prithvi-EO-2.0 ou U-Net siamesa) roda no **Colab**, operada pelo usuário, com gate na hora 6. |
| Q6 | Assinaturas | Todas: A (sem lastro / árvore fantasma, como indício agregado por célula), B (exploração não declarada), C (árvore declarada fora da UPA), D (volume acima do autorizado e intensidade acima de 30 m³/ha), E (data fora da validade). |
| Q7/Q12 | Imagens | **Sentinel-2** via GEE como base (Planetary Computer como fallback). **CBERS-4A WPM 2 m** (INPE/BDC) é a fonte de alta resolução nos casos de topo. NICFI fica como bônus (hoje sem acesso). Amazonia-1 está descartado (WFI ~64 m, menor que uma clareira). |
| Q8 | Volume | Calibração **IF100 ↔ distúrbio observado** por célula de 100 m, com regressão quantílica. No corte raso: área × estoque/ha. Incerteza via **Monte Carlo p10/p50/p90**. A flag forte só dispara quando o p10 ultrapassa o limite. |
| Q9 | Acurácia | **Block CV espacial**, cobertura empírica do intervalo p10–p90, **MODEL_CARD** e tela **Confiabilidade**. |
| Q10 | Equipe | Usuário + agentes. O usuário cuida de: autenticação GEE, execução no Colab, validação visual e ensaio. |
| Q11 | GEE | Projeto `project-f5ab0bff-aa9b-4cb2-97d`. Testados com sucesso: S2, GEDI L4A e Meta Canopy Height. NICFI: sem acesso. |
| Q13 | Jornada | Três telas: **Triagem → Dossiê → Confiabilidade**, mais o botão "Analisar nova autorização". |
| Q14/Q15 | Escopo | Polo **AMACRO**: Sul do AM (Humaitá, Lábrea, Novo Aripuanã, Manicoré, Canutama) + Porto Velho/Candeias (RO). Imagem em **30–60 POAs** e **10–20 ASV/UAS**. CBERS só nos 3–5 casos de topo. |
| Q16 | Exposição | Nº da AUTEX visível no app, sem nome e sem CNPJ. Linguagem de triagem. Nº mascarado nos slides. Selo experimental em todas as telas. |
| Q17 | Nome | **Lastro** |
| Q18 | Entregáveis | App offline com 3 telas, MODEL_CARD/README/docs, deck de pitch de 5 min, vídeo de backup e git com commits por marco. |
| Q19 | DOF | DOF Transportes (zip de 4,4 GB) baixado em background e filtrado pelo polo. Camada complementar, cortável. |
| Q20 | Ao vivo | Análise ao vivo leve: regras documentais + S2/GEE + LightGBM, em menos de 60 s. O padrão da demo é o cache. |

### Fatos verificados na sondagem (pasta `_sondagem/`)

- **PAMGIA/Sinaflor**: `SINAFLORGEO/sinaflor_proj_externo_merge_a/FeatureServer/6` tem 87.063 polígonos, 16.893 deles no bioma Amazônia (PMFS/POA 11.922; ASV 3.229; UAS 1.464). A chave de ligação é `nu_autorizacao`.
- **POA Amazônia Legal** (CSV de 90 MB): volume por espécie e por UPA. Cruza com 1.786 polígonos. Intensidade mediana de 22,7 m³/ha (p90 de 27,4).
- **Volumes Explorados IF100** (zip de 50 MB): **cada árvore explorada com lat/lon, espécie, volume autorizado x explorado e data**. Entre 2023 e 2026 são 916 POAs com polígono e cerca de 1,15 milhão de árvores. A razão explorado/autorizado tem mediana de 0,96 (p90 de 1,11; máximo de 1,49).
- **ASV CSV**: não tem coluna de volume. O volume da ASV vem do **DOF Autorizações (AUTEX)**, um zip de 13 MB.
- **BDC/INPE STAC**: `CB4A-WPM-PCA-FUSED-1` (2 m RGB), com 43 cenas desde 2023 em Cujubim/RO. O asset `tci` tem cerca de 4 GB por cena, o que exige leitura por janela.
- **Problema de dados**: lat/lon do IF100 e da UPA aparecem **sem sinal negativo** (ex.: `60,412819`). É preciso normalizar: `lon = -|lon|`, e para a latitude escolher o sinal que cai dentro ou perto do polígono da autorização.

---

## 2. Arquitetura

```
fontes (PAMGIA, IBAMA CSV, DOF, TerraBrasilis, GEE S2/GEDI/Canopy, BDC CBERS)
   │  pipeline/ingest  (cache + manifest de proveniência)
   ▼
data/processed/*.parquet  (autorizacoes, upas, arvores_if100, deter, prodes, dof)
   │  pipeline/imagery   → rasters por AOI (S2 pré/pós, Δíndices, CBERS recorte)
   │  pipeline/detect    → baseline + LightGBM → máscara de distúrbio
   │  pipeline/grid      → células 100 m: volume declarado, distúrbio, rótulos
   │  pipeline/volume    → calibração quantílica + Monte Carlo
   │  pipeline/rules     → flags A–E, F1–F7, score
   ▼
data/artifacts/  (contrato JSON/GeoJSON/PNG, lido pela API)
   │  api/ FastAPI (somente leitura + POST /analyze ao vivo)
   ▼
web/ React + Vite + MapLibre  →  Triagem · Dossiê · Confiabilidade
```

### Estrutura do repositório e quem é dono de cada pasta (evita conflito entre agentes)

```
SOLUCAO-FINAL/
  contracts/          # ORQUESTRADOR: schemas JSON + mocks (congelados na H0:45)
  pipeline/ingest/    # AG-DADOS
  pipeline/imagery/   # AG-IMAGEM
  pipeline/detect/    # AG-ML
  pipeline/grid/ pipeline/volume/   # AG-ML (volume) + AG-DADOS (grid)
  pipeline/rules/ pipeline/export/  # AG-REGRAS
  api/                # AG-API
  web/                # AG-FRONT
  colab/              # AG-COLAB
  docs/ pitch/        # AG-DOCS
  tests/              # cada agente, no seu subdiretório
  data/raw|processed|artifacts   (gitignored, exceto artifacts de demo)
```

### Contrato de artefatos (congelado na Fase 0)

- `data/artifacts/index.json`: lista de casos com `autex, tipo, uf, municipio, area_autorizada_ha, validade{ini,fim}, volume_autorizado_m3, volume_declarado_explorado_m3, volume_estimado{p10,p50,p90}, flags[{codigo,severidade,confianca}], score, source_mode(real|simulado), processado_em`.
- `cases/{autex}/dossier.json`: tudo do índice, mais `flags[].evidencias[]`, `parametros_volume`, `imagens[{id,sensor,data,png,bounds,nuvem_pct}]`, `proveniencia[{fonte,url,consultado_em,versao}]`, `limitacoes[]`, `legal_conclusion:false`.
- `cases/{autex}/*.geojson`: `upa`, `buffer`, `arvores` (amostradas ou agrupadas acima de 5 mil), `celulas` (100 m: `vol_declarado`, `disturbio`, `vol_p10/p50/p90`, `classe`), `mudanca`, `deter`, `prodes`.
- `cases/{autex}/img/*.png`: `s2_pre`, `s2_pos`, `dndvi`, `cbers_pre`, `cbers_pos`, todos em EPSG:4326 com bounds, para o MapLibre.
- `metrics/detector.json`, `metrics/calibracao.json`, `metrics/montecarlo.json`.

---

## 3. Método (o que cada agente implementa)

### 3.1 Geoprocessamento
- Todas as áreas e distâncias são calculadas em SIRGAS 2000 / UTM, com zona automática por AOI (polo: 20S/EPSG:31980 e 21S/EPSG:31981 a leste de 60° W).
- AOI = polígono + buffer de 2 km, **menos os polígonos de outras autorizações** (para não acusar vizinho licenciado).
- Tolerância de borda de 20 m (2 px S2). Grade de células de 100 m alinhada à UTM.

### 3.2 Imagens
- **Data pré**: mediana S2 da estação seca (jun–set) anterior à primeira `DATA_DA_EXPLORACAO`. **Data pós**: mediana da estação seca logo após a última exploração, com no máximo cerca de 6 meses de defasagem, porque a clareira fecha. Máscara SCL + `s2cloudless`.
- Índices: ΔNDVI, ΔNBR, ΔNDMI e ΔNDFI simplificado.
- CBERS-4A WPM: leitura por janela via `/vsicurl/`. **Primeira tarefa do AG-IMAGEM é verificar se o arquivo é COG.** Se não for, usar `CB4A-WPM-L4-DN-1` ou o recorte do thumbnail como camada visual.

### 3.3 Detector (distúrbio por pixel e por célula)
- Baseline: Δíndices + Otsu + morfologia.
- LightGBM: features Δ e textura. Rótulos: PRODES (corte raso) e **DETER classes `CS_GEOMETRICO`/`CS_DESORDENADO`/`DEGRADACAO`** (corte seletivo). Negativos amostrados em floresta estável.
- **Separação anti-circularidade**: o detector é treinado só com rótulos INPE. O IF100 serve apenas para a calibração de volume.
- Validação: GroupKFold por blocos de 5 km. Métricas: IoU, F1, precisão, recall e matriz de confusão, sempre contra o baseline.

### 3.4 Volume e incerteza
- **POA**: por célula, `vol_declarado_m3/ha` (IF100) ~ `f(distúrbio)`. Regressão quantílica (LightGBM quantile q10/q50/q90). O treino usa células de UPAs "limpas", sem DETER no buffer e sem embargo. Validação GroupKFold por UPA. Reportar R², MAE e **cobertura empírica do intervalo p10–p90**.
  - **A (sem lastro)**: na soma da UPA, `vol_declarado − vol_p90(distúrbio)` > 0, e em células concentradas.
  - **B (não declarado)**: distúrbio dentro ou fora da UPA sem árvores declaradas na célula → volume p10/p50/p90.
- **ASV**: `área_desmatada × V_ha`, com `V_ha` = volume AUTEX / área autorizada. Checagem independente via GEDI L4A, convertendo AGB em volume com WD e BEF. **Se o estoque declarado estiver muito acima do GEDI, sinaliza crédito inflado.**
- Monte Carlo com 10 mil amostras e distribuições explícitas por parâmetro, gravadas em `parametros_volume`.

### 3.5 Regras e score
| Flag | Regra | Fonte |
|---|---|---|
| A / F4 | Volume declarado ou transportado acima do p90 estimado pela imagem | IF100, DOF, M4 |
| B / F1 | Distúrbio fora da UPA (além de 20 m) ou dentro sem declaração | detector |
| C | Árvore IF100 fora do polígono (além de 20 m) | geometria |
| D / F3 / F7 | Explorado acima do autorizado (por árvore, por espécie e no total); intensidade acima de 30 m³/ha (teto CONAMA 406/2009, a confirmar na norma) | IF100, POA |
| E / F5 | Data de exploração ou de mudança fora da validade | IF100, AUTEX, imagem |
| F2 | ASV: área desmatada acima da autorizada | detector |
| F6 | Mudança sobre UC, TI ou embargo | IBAMA, ICMBio, FUNAI |

Score = Σ peso × severidade × confiança, normalizado de 0 a 1 e usado **só para ordenar**. Cada flag mostra a evidência e o grau de confiança.

---

## 4. Cronograma de 8 horas

Legenda: 🧑 = ação humana do usuário · 🤖 = subagente · 🎛 = orquestrador (sessão principal)

### Fase 0 — Fundação (H0:00–0:45) · sequencial 🎛
1. `git init`, estrutura de pastas, `uv` com geopandas, rasterio, pyproj, shapely, earthengine-api, pystac-client, lightgbm, scikit-learn, fastapi, uvicorn e pytest. Scaffold Vite + React + MapLibre.
2. 🧑 **Autenticar o GEE**: `uv run earthengine authenticate` e depois `ee.Initialize(project='project-f5ab0bff-aa9b-4cb2-97d')`. Leva cerca de 5 min.
3. Contrato: `contracts/*.schema.json` + **mock completo de 2 casos** (POA e ASV) em `data/artifacts-mock/`.
4. Downloads em background: DOF Transportes (4,4 GB), DOF Autorizações, DETER/PRODES do polo, polígonos PAMGIA com geometria do polo.
5. Commit `M0`.

### Fase 1 — Construção paralela (H0:45–3:30) · 6 agentes
| Agente | Entrega na H3:30 |
|---|---|
| 🤖 AG-DADOS | `autorizacoes.parquet`, `upas.parquet`, `arvores_if100.parquet` (coordenadas normalizadas e testadas), DETER/PRODES/UC/TI/embargos do polo, regras C/D/E rodando em **todas** as autorizações do polo. Pré-triagem com o top 60 POA e 20 ASV. |
| 🤖 AG-IMAGEM | Exportador GEE de S2 pré/pós por AOI (com fallback para Planetary Computer), Δíndices, PNGs. Verificação COG do CBERS e recorte de 1 caso. |
| 🤖 AG-ML | Baseline + LightGBM treinado num primeiro lote de AOIs, com block CV e `metrics/detector.json`. |
| 🤖 AG-API | FastAPI servindo o contrato a partir do mock (troca de raiz por variável de ambiente) e stub de `POST /analyze`. |
| 🤖 AG-FRONT | As 3 telas sobre o mock: lista e mapa da triagem, dossiê com slider antes/depois, camadas, cards de volume e flags, e Confiabilidade. Identidade visual do RAIZTRACE. |
| 🤖 AG-COLAB | `colab/lastro_dl.ipynb` auto-contido: chips S2 com máscaras PRODES/DETER via GEE, fine-tune Prithvi-EO-2.0 (fallback U-Net SSL4EO), métricas no mesmo block CV e exportação de predições das AOIs. |

🧑 **H2:00**: subir e rodar o notebook no Colab com GPU. Ele roda sozinho, cerca de 2 a 3 h.

**Gate G1 (H3:30)**: **1 POA real ponta a ponta** (dados → S2 → detector → células → artefato → UI). Se falhar, todos os agentes param a expansão e fecham esse fluxo.

### Fase 2 — Inteligência e escala (H3:30–6:00)
| Agente | Entrega |
|---|---|
| 🤖 AG-ML (volume) | Calibração quantílica com GroupKFold por UPA, `metrics/calibracao.json` (cobertura do intervalo) e Monte Carlo. |
| 🤖 AG-REGRAS | Motor de flags A–E e F1–F7, score e exportador de `dossier.json`, com testes. |
| 🤖 AG-IMAGEM | Escala para 30–60 POAs e 10–20 ASVs. CBERS nos top 3–5. GEDI/Canopy nas ASVs. |
| 🤖 AG-API | Leitura dos artefatos reais. `POST /analyze/{autex}` ao vivo: regras + S2 + LightGBM, com timeout de 60 s e fallback para o cache. |
| 🤖 AG-FRONT | Integração com a API real, estados de carregamento e erro, exportação do dossiê (impressão/PDF) e selo experimental. |
| 🤖 AG-DOCS | MODEL_CARD, SOURCES (proveniência e datas), METHOD, README e esqueleto do deck. |
| 🤖 AG-DADOS | Cenário **SIMULAÇÃO** de reserva (anomalia injetada sobre geografia real) e filtro do DOF. |

**Gate G2 (H6:00)**: congelar as features.
- 🧑 Trazer os artefatos do Colab. O DL entra como "modelo 3" **só se superar o LightGBM** na validação. Se não superar, vira slide com as métricas.
- 🧑 **Validação visual** dos 3–5 casos de topo (cerca de 15 min). Escolher **2 casos de demo**: 1 POA e 1 ASV.

### Fase 3 — Polimento (H6:00–7:15)
- 🤖 AG-FRONT: polimento visual e roteiro de cliques.
- 🤖 AG-DOCS: deck de 5 min em HTML (problema → dados → método → casos → acurácia → limites → impacto → próximos passos).
- 🤖 AG-QA: testes de pytest (volume, geometria, regras, normalização de coordenadas) e Playwright smoke. Teste offline com a rede desligada.
- 🎛 Revisão adversarial de linguagem: nenhum "fraude" ou "ilegal" afirmativo.

### Fase 4 — Congelamento e ensaio (H7:15–8:00)
- 🎛 Commit `M-final` e tag. 🤖 Gravação de vídeo e GIF via Playwright.
- 🧑 **Ensaio do pitch** com o app aberto em modo offline.

---

## 5. Linhas de corte (cortar nesta ordem se atrasar)
1. NICFI (já fora do caminho).
2. DOF Transportes (camada complementar).
3. DL do Colab (vira slide).
4. Análise ao vivo (o botão abre o cache).
5. CBERS (fica só o S2, e a lupa vira slide).
6. ASV: reduzir a 1 caso.
7. **Nunca cortar**: 1 POA real ponta a ponta, as flags C/D/E, o volume com p10/p50/p90, a tela Confiabilidade e o selo experimental.

## 6. Riscos principais
| Risco | Mitigação |
|---|---|
| Nuvem no par pré/pós | Mediana da estação seca. Escolher casos com par limpo na pré-triagem. |
| Clareira fecha antes da imagem pós | Janela de no máximo 6 meses. Mostrar "não observável" em vez de acusar. |
| CBERS não é COG (4 GB) | Verificação na Fase 1. Fallback para o produto DN COG ou só a camada visual. |
| Cota ou latência do GEE | Cache local de tudo. Fallback para Planetary Computer. |
| Calibração contaminada por fraude | UPAs limpas e ajuste quantílico robusto. Declarar a limitação no MODEL_CARD. |
| Sinal das coordenadas do IF100 | Normalização com teste. Validar contra o polígono. |
| Conflito entre agentes | Pasta própria por agente, contrato congelado e commits por marco. |

## 7. Checklist do usuário (ações humanas)
- [ ] H0:15: `earthengine authenticate` nesta máquina.
- [ ] H2:00: rodar `colab/lastro_dl.ipynb` no Colab com GPU.
- [ ] H6:00: trazer as saídas do Colab e validar visualmente os casos de topo.
- [ ] H7:30: ensaiar o pitch e revisar o deck.
- [ ] (Opcional) Cadastro no Planet NICFI, como bônus.
