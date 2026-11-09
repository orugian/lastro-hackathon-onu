# Detector de distúrbio Lastro

Implementação experimental para priorizar fiscalização. Não constitui prova.

## Uso no MVP

A consulta da demo usa os resultados já exportados em `data/artifacts/`; não executa inferência. Para análise de novas imagens, prepare dados e modelos conforme o [README principal](../../README.md#análise-ao-vivo-preparação-adicional).

- `predict.prever(stack_path, out_dir, model_dir='data/processed/ml')`: executa LightGBM com `lgbm_detector.txt` e `threshold.json` previamente preparados; retorna `prob_tif`, `mask_tif` e `poligonos_geojson`.
- `selecao.prever_volume`: usa sempre o LightGBM, como a calibração de volume.
- `selecao.prever_espacial`: confirma a detecção LightGBM pela U-Net (regra AND), quando o peso ONNX está disponível. Requer `prob.tif` já calculado na mesma grade.
- `dl.prever`: inferência U-Net por janelas, em CPU com ONNX Runtime.
- `common.features(array)`: calcula os atributos do detector a partir do stack de 16 bandas.

`LASTRO_DETECTOR=lightgbm` desabilita a confirmação U-Net. O peso `models/lastro_unet.onnx` é distribuído por Git LFS. O treinamento original da U-Net e as ferramentas de avaliação offline não fazem parte deste MVP.

## Preparar LightGBM

Com os dados de ingestão preparados, uma conta autenticada no Earth Engine e `LASTRO_EE_PROJECT` definido:

```sh
uv run python -m pipeline.detect.dataset
uv run python -m pipeline.detect.train
```

`train` monta o dataset se ainda não existir. A coleta usa cache por bloco e consulta os serviços públicos GEE/INPE. Pode demorar e depende da disponibilidade e das permissões desses serviços.

## Contrato de imagem

Stack em reflectância 0–1, com bandas na ordem:

```text
pre_B2, pre_B3, pre_B4, pre_B8, pre_B11, pre_B12,
pos_B2, pos_B3, pos_B4, pos_B8, pos_B11, pos_B12,
dNDVI, dNBR, dNDMI, valid_mask
```

Deltas são **pós menos pré**. B11/B12 têm resolução nativa de 20 m, reamostradas na grade de 10 m; isso não cria detalhe espectral de 10 m. O arquivo precisa de CRS e máscara de validade. Nodata: `-9999` para probabilidade e `255` para máscara. Polígonos são exportados em EPSG:4326, com área calculada em UTM.

## Métricas e limitações

As métricas históricas, os protocolos de validação espacial e os limites dos rótulos DETER/PRODES estão no [model card](../../docs/MODEL_CARD.md). As amostras são enriquecidas em alertas e não representam a prevalência regional. Há autocorrelação espacial, rótulos fracos e ausência de validação temporal independente. O score do detector não é probabilidade calibrada de irregularidade.
