# AG-ML: detector de distúrbio (baseline + LightGBM) com validação espacial

**Suas pastas:** `pipeline/detect/`, `tests/detect/`, `data/processed/ml/`, `data/artifacts/metrics/detector.json`.

## Objetivo
Construir o detector de distúrbio florestal por pixel, para Sentinel-2 a 10 m, que cobre corte raso e corte seletivo/degradação, junto com métricas honestas. Ele precisa ser um **modelo treinado** (LightGBM) comparado a um **baseline sem treino**.

## Dados de entrada (você mesmo obtém)
- **Imagens**: use o Google Earth Engine diretamente para montar o conjunto de treino. É mais rápido do que esperar o AG-IMAGEM.
  - `ee.Initialize(project='project-f5ab0bff-aa9b-4cb2-97d')`
  - Coleção `COPERNICUS/S2_SR_HARMONIZED`, com máscara de nuvem `COPERNICUS/S2_CLOUD_PROBABILITY` < 40 + SCL, e mediana.
  - Par pré = jun–set do ano N−1 e pós = jun–set do ano N, com N ∈ {2022, 2023, 2024}.
- **Rótulos INPE** (TerraBrasilis WFS `https://terrabrasilis.dpi.inpe.br/geoserver/ows`, `outputFormat=application/json`, `srsName=EPSG:4326`):
  - Positivos de corte raso: PRODES `prodes-legal-amz:yearly_deforestation`, do ano N.
  - Positivos de corte seletivo e degradação: DETER `deter-amz:deter_amz`, com `classname` em CS_DESORDENADO, CS_GEOMETRICO, DEGRADACAO e DESMATAMENTO_CR, e `view_date` entre out/N−1 e set/N.
  - Negativos: pixels de floresta estável, fora de qualquer PRODES ou DETER de 2008+ e dentro da floresta (use a camada `prodes-legal-amz:no_forest` / `residual`, ou NDVI pré > 0,75).
  - Se o AG-DADOS já tiver gravado `data/processed/deter.parquet` / `prodes.parquet`, reutilize. Se não, baixe por conta própria e salve em `data/processed/ml/`.
- **Região de treino**: o polo AMACRO (bbox -66,-10,-60,-6.5).
  - Amostre de 30 a 60 tiles de 5 × 5 km que contenham rótulos positivos e floresta.
  - **Não use os tiles das autorizações da demo como teste.** Isso não é possível ainda, porque a pré-triagem sai do AG-DADOS em paralelo. Se `data/processed/pretriagem.csv` existir, exclua aquelas AOIs; se não existir, registre isso como limitação.

## Features por pixel
Bandas pré e pós (B2, B3, B4, B8, B11, B12), NDVI/NBR/NDMI pré e pós, Δ de cada, e opcionalmente textura (desvio padrão local 3×3 de ΔNDVI) e NDFI simplificado. Use a mesma ordem de bandas do stack do AG-IMAGEM:
`pre_B2,pre_B3,pre_B4,pre_B8,pre_B11,pre_B12,pos_B2..pos_B12,dNDVI,dNBR,dNDMI,valid_mask`.
Exponha uma função que recebe esse stack.

## Entregas
1. `pipeline/detect/dataset.py`: monta o dataset amostrado. Use `ee.Image.stratifiedSample` ou sampleRegions com `classBand`, o que é rápido e evita baixar rasters inteiros, com cerca de 50–150 mil pixels balanceados e uma coluna `bloco` (id do tile de 5 km) para a validação. Grava `data/processed/ml/dataset.parquet`.
2. `pipeline/detect/baseline.py`: ΔNDVI/ΔNBR + limiar de Otsu + abertura morfológica. Função `prever_baseline(stack_path) -> prob/mask`.
3. `pipeline/detect/train.py`: LightGBM binário (distúrbio vs estável) com **GroupKFold por `bloco` (k=5)**.
   - Calcule para o baseline e para o LightGBM: IoU, F1, precisão, recall, matriz de confusão e número de pixels de teste.
   - Escolha o limiar na validação (maximizando F1).
   - Salve o modelo em `data/processed/ml/lgbm_detector.txt` (formato nativo, não pickle) + `threshold.json`.
   - Grave `data/artifacts/metrics/detector.json` no formato `MetricsDetector` de `contracts/models.py`.
     - `protocolo`: descreva o protocolo exato.
     - Inclua métricas separadas por tipo de rótulo (corte raso vs seletivo/degradação) em `obs`.
4. `pipeline/detect/predict.py`: `prever(stack_path, out_dir) -> {"prob_tif", "mask_tif", "poligonos_geojson"}`.
   - Gera `prob.tif` e máscara binária.
   - Gera polígonos vetorizados com área mínima de 0,1 ha (`rasterio.features.shapes`), em GeoJSON EPSG:4326, com `area_ha` e `prob` média.
   - Funções importáveis por outros agentes.
5. Testes em `tests/detect/`: Otsu sobre um array sintético, shape do predict e ausência de vazamento (nenhum bloco ao mesmo tempo em treino e teste do mesmo fold).

## Honestidade obrigatória
- Rótulos PRODES/DETER têm área mínima (cerca de 3 ha para DETER, 6,25 ha para PRODES) e não captam todas as clareiras pequenas. Diga isso no `obs`.
- Não reporte acurácia de pixel aleatório. Só o GroupKFold espacial.
- Se o LightGBM não superar o baseline, reporte assim mesmo.

## Critério de pronto
`uv run python -m pipeline.detect.train` gera o modelo e `detector.json` válido (valide com `MetricsDetector.model_validate`). `uv run python -m pipeline.detect.predict <stack.tif>` funciona num stack gerado por você via GEE, de mesma ordem de bandas, numa AOI do polo. Os testes passam. No relatório: tabela de métricas e tempo de treino.
