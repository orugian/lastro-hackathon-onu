# AG-IMAGEM: aquisição e pré-processamento de imagens (Sentinel-2 via GEE e CBERS-4A via INPE)

**Suas pastas:** `pipeline/imagery/`, `tests/imagery/`, `data/processed/imagery/`.

## Objetivo
Dada uma AOI (polígono EPSG:4326) e uma janela de datas, produzir:
- um par pré/pós de **Sentinel-2** em formato analítico (GeoTIFF multibanda em UTM a 10 m, com Δ-índices e máscara de qualidade);
- PNGs de visualização para o front;
- para casos selecionados, recortes **CBERS-4A WPM 2 m** pré e pós.

## API Python que você deve expor (outros agentes vão importar)
```python
# pipeline/imagery/s2.py
def baixar_par_s2(autex: str, aoi_4326: shapely.Geometry, pre: tuple[str,str], pos: tuple[str,str],
                  out_dir: Path, escala_m: int = 10) -> dict:
    """Grava out_dir/s2_stack.tif (UTM, 10 m) com bandas, nesta ordem:
       pre_B2,pre_B3,pre_B4,pre_B8,pre_B11,pre_B12, pos_B2..pos_B12, dNDVI, dNBR, dNDMI, valid_mask(0/1)
       e out_dir/s2_pre.png, s2_pos.png (RGB realce), dndvi.png (RGBA, só quedas, transparente no resto).
       Retorna {"stack": path, "crs": "EPSG:...", "bounds_4326": [...], "nuvem_pct_pre": x, "nuvem_pct_pos": y,
                "n_cenas_pre": n, "n_cenas_pos": n, "rotulo_pre": "...", "rotulo_pos": "..."}"""

def janelas_automaticas(data_expl_min: str, data_expl_max: str, validade_ini: str) -> tuple[tuple, tuple]:
    """pre = estação seca (jun-set) do ano anterior ao início da exploração (ou da validade, se não houver IF100);
       pos = de data_expl_max até data_expl_max+120 dias (clareira fecha rápido); se < 3 cenas limpas, expandir até 180 dias."""

# pipeline/imagery/cbers.py
def recorte_cbers(aoi_4326, data_alvo: str, out_png: Path, janela_dias=120, max_px=1600) -> dict | None:
    """Busca no STAC BDC a cena CB4A-WPM-PCA-FUSED-1 mais próxima de data_alvo, com a AOI coberta.
       Lê só a janela (COG) e grava PNG. Retorna {"png", "data", "bounds_4326", "item_id"} ou None."""
```

## Fatos verificados
- GEE: `ee.Initialize(project='project-f5ab0bff-aa9b-4cb2-97d')`. A coleção `COPERNICUS/S2_SR_HARMONIZED` funciona.
  - Use máscara de nuvem `COPERNICUS/S2_CLOUD_PROBABILITY` (prob < 40), com join, + SCL (excluir 3, 8, 9, 10, 11), e faça a **mediana** do período.
  - **Download**: AOIs pequenas (até cerca de 10 × 10 km a 10 m) funcionam com `ee.data.computePixels` (formato `GEO_TIFF`) ou `image.getDownloadURL({'scale':10,'crs':utm,'region':...,'format':'GEO_TIFF'})`.
  - O limite é de cerca de 48 MB por request. Se a AOI for maior, divida em tiles e faça mosaico com rasterio.
  - Faça cache: se `s2_stack.tif` existe, não refaça.
- Índices:
  - NDVI = (B8 − B4) / (B8 + B4)
  - NBR = (B8 − B12) / (B8 + B12)
  - NDMI = (B8 − B11) / (B8 + B11)
  - Δ = pós − pré, ou seja, uma queda é negativa.
- **CBERS-4A WPM (INPE BDC)**: STAC em `https://data.inpe.br/bdc/stac/v1/`, coleção `CB4A-WPM-PCA-FUSED-1`.
  - O asset `tci` é um GeoTIFF **COG** RGB uint8 de 2 m (cerca de 4 GB, tiled 512, com overviews). O CRS do exemplo é EPSG:32720.
  - Leia com `rasterio.open('/vsicurl/<href>')` e `rasterio.windows.from_bounds` na AOI reprojetada para o CRS da cena. Configure `GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` e `CPL_VSIL_CURL_ALLOWED_EXTENSIONS=.tif`.
  - Busca: POST `/search` com `collections`, `intersects` ou `bbox`, e `datetime`. Os metadados de nuvem estão vazios; avalie a nuvem pelo brilho, contando a fração de pixels com média RGB > 200, e escolha a melhor cena.
  - Pode haver bordas NoData (0,0,0). Verifique se a AOI está coberta em mais de 90%.
- **Fallback** se o GEE falhar: Planetary Computer STAC `sentinel-2-l2a` com `planetary_computer.sign` e `odc-stac` (ou rasterio direto). Só implemente se o GEE falhar de verdade.

## Entregas
1. `pipeline/imagery/s2.py` + `pipeline/imagery/cbers.py` + `pipeline/imagery/render.py`.
   - `render.py` gera PNGs com realce de percentil 2–98, e também PNG a partir de máscara/probabilidade, para outros agentes usarem.
   - Os PNGs devem ser em **EPSG:4326** (reprojete o raster para 4326 antes de renderizar), para o MapLibre sobrepor com `bounds`. Largura máxima de 1600 px.
2. `pipeline/imagery/run_batch.py --pretriagem data/processed/pretriagem.csv --top N`:
   - processa os N primeiros (AOI = polígono da autorização + 2 km, lido de `data/processed/autorizacoes.parquet`);
   - grava em `data/processed/imagery/{autex}/` com um `meta.json`;
   - roda em paralelo, com 4 threads.
   - **Esses arquivos de entrada são produzidos pelo AG-DADOS em paralelo.** Enquanto não existirem, desenvolva e teste com uma AOI fixa de teste: o polígono real da autorização `20132202420257`, ou um retângulo de 4 × 4 km em lon -63.10, lat -7.62. A AOI deve ter floresta com exploração por volta de 2024.
3. Teste de ponta a ponta numa AOI real do polo, com pré = jun–set/2023 e pós = jun–set/2024. Informe tempo, tamanho, % de nuvem e mostre que `dNDVI` tem quedas plausíveis.
4. `recorte_cbers` testado numa AOI do polo, com uma data pré e uma pós. Informe as datas e a cobertura obtidas.
5. Opcional, se sobrar tempo: `pipeline/imagery/gedi.py`, com a média de AGB (GEDI L4A, `LARSE/GEDI/GEDI04_A_002_MONTHLY`, banda `agbd`, filtro `l4_quality_flag == 1`) e de altura do dossel (`projects/meta-forest-monitoring-okw37/assets/CanopyHeight`) para uma AOI, usando `reduceRegion`.

## Critério de pronto
`uv run python -m pipeline.imagery.run_batch --top 3` (ou o teste com AOI fixa) grava stacks e PNGs válidos. `uv run pytest tests/imagery` passa (testes leves, com mock de rede quando possível). Inclua no relatório a contagem de cenas e o percentual de nuvem obtidos.
