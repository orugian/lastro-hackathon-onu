# AG-COLAB: notebook de deep learning (para rodar no Google Colab com GPU)

**Suas pastas:** `colab/`.

## Objetivo
Um notebook **auto-contido** `colab/lastro_dl.ipynb`. O usuário vai subi-lo no Colab (GPU T4/L4/A100), clicar em "Run all" e baixar um zip de resultados. O notebook treina um segmentador de distúrbio florestal com deep learning e o compara com o detector LightGBM local, usando o mesmo protocolo de validação espacial.

## Requisitos
1. **Primeira célula**: instruções em markdown para o usuário, em português e no máximo 8 linhas: o que fazer, onde autenticar e o que baixar no fim.
2. **Autenticação GEE no Colab**: `ee.Authenticate()` + `ee.Initialize(project='project-f5ab0bff-aa9b-4cb2-97d')`.
3. **Geração de chips via GEE**:
   - Região do polo AMACRO (bbox -66,-10,-60,-6.5).
   - Pares Sentinel-2 `COPERNICUS/S2_SR_HARMONIZED`, mediana jun–set do ano N−1 (pré) e do ano N (pós), N ∈ {2022, 2023, 2024}, com máscara de nuvem `COPERNICUS/S2_CLOUD_PROBABILITY` < 40.
   - 6 bandas (B2, B3, B4, B8, B11, B12) pré + 6 pós.
   - Rótulos: PRODES do ano N + DETER (classes CS_DESORDENADO, CS_GEOMETRICO, DEGRADACAO, DESMATAMENTO_CR) do período, vindos do TerraBrasilis WFS (`https://terrabrasilis.dpi.inpe.br/geoserver/ows`, camadas `prodes-legal-amz:yearly_deforestation` e `deter-amz:deter_amz`, `outputFormat=application/json`).
     - Baixe os vetores com requests, rasterize localmente com rasterio na grade do chip.
   - Chips de 224×224 px a 10 m, baixados com `ee.data.computePixels` (NPY ou GEO_TIFF) em paralelo (ThreadPool de 8–16).
   - Meta de 400 a 1.500 chips, com no mínimo 50% contendo positivo.
   - Cada chip recebe um `bloco` (grade de 25 km) para split espacial.
   - Cache em `/content/chips` e opção de salvar no Google Drive.
4. **Modelo principal**: **Prithvi-EO-2.0** (`ibm-nasa-geospatial/Prithvi-EO-2.0-300M-TL`, ou a versão 100M se faltar memória) via **TerraTorch**, em tarefa de segmentação, com entrada multitemporal de 2 frames × 6 bandas (as bandas HLS do Prithvi são Blue, Green, Red, NIR Narrow, SWIR1, SWIR2, o que corresponde a B2, B3, B4, B8A/B8, B11, B12).
   - Fine-tune de 10 a 20 épocas com early stopping.
   - **Fallback automático**: se o TerraTorch ou o Prithvi falhar na instalação, ou faltar memória, use uma **U-Net siamesa** com `segmentation_models_pytorch` (encoder ResNet34, ImageNet) e entrada de 12 canais (concat pré + pós), ou os pesos SSL4EO-S12 do `torchgeo`, se fácil.
   - Faça a lógica com try/except e registre qual modelo foi usado.
5. **Validação**: split por `bloco` (treino/val/teste ≈ 70/15/15, com os blocos inteiros num único conjunto).
   - Métricas no teste: IoU, F1, precisão, recall e matriz de confusão por pixel.
   - Inclua também o mesmo cálculo para um **baseline ΔNDVI + Otsu** nos mesmos chips de teste, para ter comparação direta.
6. **Inferência nas AOIs da demo**:
   - Uma célula com uma lista editável `AOIS = [{"autex": "...", "bbox": [minx,miny,maxx,maxy], "pre": ["2023-06-01","2023-09-30"], "pos": ["2024-06-01","2024-09-30"]}]`. O usuário vai colar os valores que o orquestrador fornecer; deixe 1 exemplo funcional com bbox `[-63.12,-7.64,-63.05,-7.58]`.
   - Para cada AOI, baixe o stack do GEE (com tiles, se for maior que 224) e faça inferência com janela deslizante.
   - Grave `prob_{autex}.tif` (GeoTIFF float32, EPSG da AOI) e `mask_{autex}.tif`.
7. **Saída**: `/content/lastro_dl_resultados.zip` contendo:
   - `metrics_dl.json` no formato `{"nome": "prithvi-eo-2.0" | "unet-siamesa", "iou", "f1", "precisao", "recall", "matriz_confusao", "n_pixels_teste", "obs", "protocolo", "baseline_mesmos_chips": {...}}`;
   - as predições das AOIs;
   - 3 a 6 PNGs de exemplo (pré, pós, rótulo, predição);
   - `config.json` com tudo o que foi usado (seeds, épocas, n_chips).
   - Ao final, chame `files.download(...)`.
8. Robustez:
   - Seeds fixas.
   - Prints de progresso.
   - Tempo total-alvo de no máximo 2 h numa T4. Ofereça uma variável `MODO_RAPIDO = True`, que reduz chips e épocas para cerca de 30 min.
   - Nada de interação manual além da autenticação.

## Entregas
- `colab/lastro_dl.ipynb` (JSON de notebook válido; gere com `nbformat` via `uv run --with nbformat python ...` e valide com `nbformat.validate`).
- `colab/README.md` com 5 passos para o usuário.
- Teste local leve:
  - Rode, com `uv run --with nbformat --with nbconvert`, apenas uma verificação sintática de cada célula de código (`ast.parse`, ignorando linhas que começam com `!` ou `%`).
  - Teste localmente a função de rasterização de rótulos e a de geração de chip para 1 chip, usando o GEE local (`ee.Initialize(project='project-f5ab0bff-aa9b-4cb2-97d')` já funciona nesta máquina), para garantir que a parte de dados funciona. **Não** rode o treino localmente.

## Critério de pronto
Notebook válido; geração de 1 chip e do seu rótulo verificada localmente (salve um PNG de verificação em `colab/check_chip.png`); README pronto.
