# AG-REGRAS: motor de flags, score e exportação dos artefatos (dossiê)

**Suas pastas:** `pipeline/rules/`, `pipeline/export/`, `tests/rules/`, `data/artifacts/` (exceto `metrics/`, que pertence ao AG-ML e ao AG-VOLUME).

## Contexto
Leia `contracts/models.py` (contrato v1, que é a lei), o mock `data/artifacts-mock/` (exemplo completo do formato esperado, inclusive o tom dos textos), `data/processed/README.md` e os relatórios `agentes/logs/*.final.md`.

Módulos disponíveis:
- `pipeline/grid/celulas.py`, `pipeline/imagery/*`, `pipeline/detect/predict.py`;
- `pipeline/volume/estimar.py` (`estimar_celulas`, `classificar_celulas`, `monte_carlo_upa`, `volume_corte_raso`). Este é feito em paralelo pelo AG-VOLUME. Enquanto ele não existir, use um stub local com a mesma assinatura em `pipeline/rules/_stub_volume.py` e troque pelo real quando existir.

## Objetivo
Para cada autorização, gerar `data/artifacts/cases/{autex}/` completo e `data/artifacts/index.json`, conforme o contrato:
- **casos com imagem**: top N da `pretriagem.csv`;
- **casos só documentais**: todas as demais autorizações do polo, com `analise_imagem=false`, e apenas as flags C, D e E de `regras_doc.parquet`.

## Pipeline por caso com imagem (`pipeline/export/caso.py: processar_caso(autex) -> Dossier`)
1. Carregar a autorização, as árvores e as regras documentais. AOI = polígono + 2 km **menos os polígonos de outras autorizações** (`buffer.geojson`).
2. Garantir o stack S2 (`baixar_par_s2` + `janelas_automaticas`) e rodar `prever` do detector → `prob.tif` e polígonos de mudança. Calcular, em UTM, `dentro_upa` e `dist_limite_m` (tolerância de 20 m).
3. Células de 100 m sobre a AOI → `estimar_celulas` → `classificar_celulas` → `monte_carlo_upa`.
4. ASV/UAS: área desmatada dentro e fora → `volume_corte_raso`.
   - Estoque/ha = volume AUTEX / área autorizada, se existir; senão, GEDI via `pipeline/imagery/gedi.py`, se existir; senão, `null` com limitação registrada.
5. CBERS-4A: apenas se o caso estiver no top 5 pelo score (`recorte_cbers` pré e pós). Se falhar, siga sem ele.
6. **Flags** (`pipeline/rules/flags.py`, funções puras e testáveis, cada uma retornando `Flag` do contrato com regra textual, evidências, status, severidade e confiança):
   - **A** (POA): excesso sem lastro = Σ(vol_declarado − vol_p90) nas células `sem_lastro`. Status `indicio` se o p10 do excesso (Monte Carlo) for maior que 0 e houver pelo menos 5 células contíguas, ou se o excesso for de pelo menos 10% do volume declarado. Confiança combina a cobertura da calibração com a fração observável. Evidência com `camada: "celulas"` e `filtro: {"classe": "sem_lastro"}`.
   - **B**: polígonos de mudança fora da UPA a mais de 20 m e prob ≥ 0,5, não cobertos por outra autorização. Também conta área `nao_declarado` dentro da UPA. Inclui volume p10/p50/p90. Inclui alerta DETER coincidente como evidência adicional, citando classe e data.
   - **C**: árvores IF100 fora do polígono. Evidência com `camada: "arvores"`, `filtro: {"dentro_upa": false}`.
   - **D**: explorado > autorizado (total, por espécie e por árvore com mais de 10% acima) e intensidade > 30 m³/ha. Para ASV: p10 do volume estimado > volume autorizado.
   - **E**: exploração ou mudança fora da validade. A janela da imagem é um intervalo: se ela cruza a fronteira da validade, use `inconclusivo`.
   - **F2** (ASV/UAS): área desmatada total > área autorizada × 1,05.
   - **F6**: mudança sobre UC ou TI (se `uc.parquet`/`ti.parquet` existirem; senão, `nao_avaliado`).
   - Dados ausentes → `nao_avaliado` ou `inconclusivo`, **nunca** `sem_indicio`.
7. **Score** (`pipeline/rules/score.py`): Σ peso × severidade × confiança entre as flags com status `indicio`, normalizado com 1 − exp(−x), o que dá um valor entre 0 e 1. Pesos: A=1,0, B=1,0, D=0,8, F2=0,9, C=0,6, E=0,6, F6=1,0. Documente os pesos em `parametros` do dossiê e no código.
8. **Exportação**:
   - GeoJSON simplificado (simplify de 2–5 m em UTM, coordenadas com 6 casas decimais);
   - árvores: se houver mais de 8 mil pontos, amostre mantendo TODAS as `dentro_upa=false` e as de células `sem_lastro`;
   - PNGs via `pipeline/imagery/render.py` (`s2_pre`, `s2_pos`, `dndvi`/prob como RGBA, `cbers_pre`, `cbers_pos`);
   - `dossier.json` validado com `Dossier.model_validate`;
   - `proveniencia` com URLs e datas reais;
   - `limitacoes` específicas do caso (nuvem %, janela temporal, ausência de CBERS etc.);
   - `linha_do_tempo` (validade, primeira/última exploração, alertas DETER, datas das imagens);
   - `especies` (top 10 por volume);
   - **sem nome ou CPF/CNPJ do detentor em lugar nenhum.**
9. `pipeline/export/run.py --top N [--so-docs] [--autex X]`:
   - processa em paralelo (4 workers);
   - é tolerante a falha por caso (loga e segue);
   - gera `index.json` validado com `Index`, com `polo` e `totais` (autorizacoes_avaliadas, com_imagem, com_indicio, arvores_if100, volume_declarado_total_m3, volume_sem_lastro_p50_m3).
10. **Cenário SIMULAÇÃO de reserva**: `pipeline/export/simulado.py` copia um caso real processado. Sobre a mesma geografia e imagem, injeta:
    - "árvores fantasma": adiciona IF100 sintéticos num bloco de células sem distúrbio;
    - 3 árvores fora da UPA.
    Grava como `SIM-{autex}` com `source_mode="simulado"` e um aviso explícito em `limitacoes`, e mostra que A e C disparam.

## Linguagem
Use o tom do mock: "indício", "divergência", "prioridade de fiscalização". Nunca "fraude", "ilegal" ou "crime". Toda frase de evidência precisa ser verificável, com número, unidade e fonte.

## Testes (`tests/rules/`)
Cada flag com fixtures pequenas (shapely e GeoDataFrames em memória), incluindo os casos-limite:
- tolerância de 20 m;
- dados ausentes → `nao_avaliado`;
- janela de imagem cruzando a validade → `inconclusivo`.

Inclua também a monotonicidade do score e a validação de schema de um caso exportado.

## Critério de pronto
`uv run python -m pipeline.export.run --top 3` gera 3 casos reais completos + `index.json`. `uv run pytest tests/rules` passa. A API (`api/main.py`) com `LASTRO_ARTIFACTS=data/artifacts` serve os casos (teste com TestClient).
