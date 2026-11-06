# Detector de distúrbio LASTRO

Implementação experimental para priorizar fiscalização. Não constitui prova.

## Execução

```powershell
uv run python -m pipeline.detect.dataset
uv run python -m pipeline.detect.train
uv run python -m pipeline.detect.export_example
uv run python -m pipeline.detect.predict data/processed/ml/example_stack.tif
uv run pytest tests/detect -q --basetemp=data/processed/ml/pytest-temp
```

`train` monta o dataset se ainda não existir. A coleta usa GEE autenticado no projeto
`project-f5ab0bff-aa9b-4cb2-97d` e WFS INPE. Cache por bloco permite retomar a coleta.
Nenhum dado simulado entra nas métricas publicadas. Dados sintéticos são usados apenas
nos testes unitários, em diretório temporário separado do modelo real.

## Interfaces

- `baseline.prever_baseline(stack_path) -> (prob, mask)`: score espectral em [0,1]
  (não probabilidade calibrada), NaN fora da máscara válida; Otsu e abertura 3x3.
- `predict.prever(stack_path, out_dir, model_dir='data/processed/ml') -> dict`:
  caminhos `prob_tif`, `mask_tif`, `poligonos_geojson`. Sempre executa LightGBM;
  o melhor modelo da comparação é informado separadamente em `detector.json`.
- `common.features(array)`: última dimensão com as 16 bandas do stack.

Stack em reflectância 0–1, bandas na ordem:
`pre_B2,pre_B3,pre_B4,pre_B8,pre_B11,pre_B12,pos_B2,pos_B3,pos_B4,pos_B8,pos_B11,pos_B12,dNDVI,dNBR,dNDMI,valid_mask`.
Deltas são **pós menos pré**, conforme AG-IMAGEM. B11/B12 têm resolução nativa de
20 m, amostradas na grade de 10 m; isso não cria detalhe espectral real de 10 m.
O arquivo deve ter CRS e máscara de validade; nodata de saída: -9999 (prob) e 255
(mask). Polígonos têm área UTM >= 0,1 ha, coordenadas EPSG:4326 e média de probabilidade.

## Protocolo e limitações

36 tiles fixos de 5 km no EPSG:31980, 12 por ano (2022–2024). A seleção favorece
tiles com alertas de degradação/seletivo; não é amostra representativa de AMACRO.
Medianas jun–set, nuvem <40 e SCL excluindo 0,1,3,8,9,10,11.
Negativos: NDVI pré >0,75, fora de todos os DETER retornados e PRODES 2008+.
Positivos: PRODES do ano e DETER de outubro anterior a setembro do ano.
DETER seletivo/degradação prevalece sobre PRODES quando há sobreposição.

GroupKFold externo k=5 por bloco. Dentro de cada treino externo, holdout por bloco
(25%) escolhe limiar por F1; só então o modelo é reajustado no treino externo e
avaliado no teste externo. Os folds e limiares ficam em `validation.json`.
O modelo final usa todos os dados e mediana dos limiares internos. O baseline não
usa rótulos: Otsu em histograma de até 128 bins do tile inteiro, abertura 3x3 antes
da amostragem. A função local usa Otsu do scikit-image, podendo variar ligeiramente
pela discretização do histograma GEE. Métricas por tipo incluem os mesmos negativos.

A proximidade entre blocos não é impedida por buffer espacial; a validação ainda
pode ser otimista por autocorrelação. Não há validação temporal independente.
DETER (~3 ha) e PRODES (6,25 ha) omitem pequenas clareiras. Os rótulos são fracos,
não verdade de campo; eventos posteriores à mediana podem estar rotulados como
positivos. A amostragem balanceada altera a prevalência e as probabilidades não
são calibradas. As métricas não estimam diretamente desempenho em toda autorização.
A ausência de `pretriagem.csv` é registrada; se disponível na coleta ou treino,
blocos que cruzem autorizações com buffer de 2 km são excluídos.

`labels_*.json`, `seeds.json`, `manifest.json`, `errors.json`, `oof.parquet` e
`validation.json` permitem auditar a origem e o protocolo. A coleta consulta o
estado atual do WFS (que pode ter revisões históricas); preserve esses caches.
