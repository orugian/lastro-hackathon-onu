# AG-VOLUME: calibração imagem→volume, incerteza e Monte Carlo

**Suas pastas:** `pipeline/volume/`, `tests/volume/`, `data/processed/volume/`, `data/artifacts/metrics/calibracao.json`, `data/artifacts/metrics/montecarlo.json`.

## Contexto
Os agentes da Fase 1 já produziram (veja `data/processed/README.md` e os relatórios em `agentes/logs/*.final.md`):
- `data/processed/autorizacoes.parquet` (polígonos), `arvores_if100.parquet` (árvores declaradas exploradas com coordenada, volume e data), `regras_doc.parquet`, `pretriagem.csv`;
- `pipeline/grid/celulas.py` (`grade_celulas`, `agrega_arvores`);
- `pipeline/imagery/` (`baixar_par_s2`, `janelas_automaticas`, `recorte_cbers`, `render`) e stacks em `data/processed/imagery/{autex}/s2_stack.tif`;
- `pipeline/detect/` (`prever(stack_path, out_dir)` → `prob.tif`, máscara, polígonos) com modelo LightGBM treinado.

Leia esses módulos antes de começar. Reuse, não reimplemente.

## Objetivo
Transformar "o que a imagem mostra" em **volume (m³) com intervalo calibrado**, e medir honestamente a qualidade dessa conversão.

### 1. Dataset de calibração por célula (POA)
- Para N UPAs de calibração (meta de 40 a 120), use as autorizações POA do polo com IF100 e com o stack S2 disponível ou baixável.
  - Use `baixar_par_s2` com `janelas_automaticas`. Paralelize em 4 threads e use cache.
  - **Exclua** as que estão no top 10 da `pretriagem.csv` (reservadas para a demo) e as com DETER dentro do polígono, porque calibração "limpa" é robusta à fraude.
- Por UPA:
  - grade de 100 m (`grade_celulas`) sobre o polígono;
  - por célula, `vol_declarado` (m³, soma do `VOLUME_EXPLORADO` IF100) e `n_arvores`;
  - features da imagem agregadas na célula: fração de distúrbio (`prob` ≥ limiar do detector), média e p10 de dNDVI, dNBR, dNDMI, desvio padrão de dNDVI, prob média, fração válida (sem nuvem);
  - descarte células com fração válida < 0,7.
- Grave em `data/processed/volume/calib_celulas.parquet`.

### 2. Modelo quantílico
- LightGBM `objective="quantile"`, com α ∈ {0,1; 0,5; 0,9}. Target = `vol_declarado` (m³ por célula de 1 ha, ou seja, m³/ha). Features da imagem. Restrição monotônica crescente na fração de distúrbio e decrescente em dNDVI, se ajudar.
- **Validação: GroupKFold por UPA (k=5).**
- Métricas fora da amostra:
  - R² e MAE (da p50) por célula;
  - **cobertura empírica de [p10, p90]**, nominal 80%;
  - as mesmas métricas **agregadas por UPA** (soma das células vs soma declarada), que é a que importa para a decisão.
- Se a cobertura ficar fora de 70–90%, aplique **calibração conformal** (CQR: ajuste o intervalo com o quantil dos resíduos de conformidade num fold de calibração) e reporte antes e depois.
- Salve os modelos em `data/processed/volume/lgbm_q{10,50,90}.txt` e o ajuste conformal num JSON.
- `data/artifacts/metrics/calibracao.json` no formato `MetricsCalibracao` (`contracts/models.py`).
  - `curva` = predição p10/p50/p90 em função da fração de distúrbio (com as demais features na mediana), de 0 a 1 em 21 pontos.
  - Em `obs`, registre as métricas por UPA, o efeito conformal e as limitações: calibração contaminada se houver fraude não detectada nas UPAs "limpas"; clareira fecha; nuvem.

### 3. API de estimativa (para o AG-REGRAS)
```python
# pipeline/volume/estimar.py
def estimar_celulas(celulas_gdf, stack_path, prob_path) -> GeoDataFrame:
    """Adiciona disturbio_frac, vol_p10, vol_p50, vol_p90 (m³/célula) e frac_valida."""

def classificar_celulas(gdf) -> GeoDataFrame:
    """classe ∈ {consistente, sem_lastro, nao_declarado, sem_atividade, nao_observavel}:
       nao_observavel: frac_valida < 0.7
       sem_lastro: vol_declarado > vol_p90 (e vol_declarado >= 5 m³)
       nao_declarado: n_arvores == 0 e disturbio_frac >= limiar (ex. 0.15) e vol_p10 > 0
       consistente: demais com n_arvores > 0
       sem_atividade: resto"""

def monte_carlo_upa(gdf, n=10000, seed=0) -> dict:
    """Soma o volume da UPA amostrando de cada célula uma distribuição ajustada aos quantis (p10,p50,p90),
       por exemplo uma lognormal assimétrica ou interpolação por partes do CDF, com correlação espacial simplificada
       (um fator comum de escala por UPA ~ lognormal(0, sigma_upa), com sigma_upa estimado dos resíduos por UPA).
       Retorna {p10,p50,p90} da UPA e dos subconjuntos: sem_lastro_excesso (Σ vol_declarado − vol estimado nas
       células sem_lastro) e nao_declarado (Σ volume nas células nao_declarado)."""

def volume_corte_raso(area_ha_faixa, estoque_m3_ha: float | None, agb_mg_ha: float | None, n=10000) -> dict:
    """Para ASV/UAS: V = A × V_ha. V_ha ~ Normal(estoque declarado, 15%) se houver; senão AGB GEDI →
       volume via V_ha = AGB / (WD × BEF) × f_com, com WD ~ N(0.62, 0.05) g/cm³, BEF ~ N(1.6, 0.15) e
       f_com ~ U(0.3, 0.5), parâmetros explícitos e registrados. Retorna p10/p50/p90 + parametros (lista
       compatível com ParametroVolume)."""
```
Grave `data/artifacts/metrics/montecarlo.json` com a descrição das distribuições e de `sigma_upa`.

### 4. Testes
- `tests/volume/`:
  - a cobertura do intervalo em dados sintéticos com quantis conhecidos fica perto do nominal;
  - Monte Carlo com parâmetros fixos é reprodutível (seed);
  - `classificar_celulas` classifica corretamente casos-limite;
  - `volume_corte_raso` usa as unidades corretas, por exemplo: 100 ha × 20 m³/ha ≈ 2.000 m³ na p50.

## Critério de pronto
`uv run python -m pipeline.volume.calibrar` gera os modelos e o `calibracao.json` válido. Os testes passam. O relatório traz uma tabela de métricas: célula e UPA, antes e depois do conformal.
