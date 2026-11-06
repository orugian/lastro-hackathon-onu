# AG-DADOS: ingestão, normalização, regras documentais e pré-triagem

**Suas pastas:** `pipeline/ingest/`, `pipeline/grid/`, `tests/ingest/`, `data/processed/`.

## Objetivo
Produzir as tabelas e geometrias limpas do polo AMACRO. Rodar as regras documentais C, D e E em TODAS as autorizações do polo e gerar a lista priorizada de casos que vão para análise de imagem.

## Fatos já verificados
- **Polígonos**: ArcGIS FeatureServer `https://pamgia.ibama.gov.br/server/rest/services/SINAFLORGEO/sinaflor_proj_externo_merge_a/FeatureServer/6/query`.
  - Campos principais: `nu_autorizacao, tipo_atividade, nm_orgao, municipio, uf, dt_valid_inicio, dt_valid_fim` (epoch ms), `status_autorizacao, area_pamgia_ha, bioma_pamgia, presen_uc_fed, presen_ti, nu_car_imovel, dt_atualizacao`.
  - Valores de `tipo_atividade`: "PMFS/POA", "Autorização de Supressão de Vegetação - ASV", "Uso Alternativo do Solo", "Exploração de Floresta Plantada".
  - Paginação: `resultOffset` + `resultRecordCount=2000` até `exceededTransferLimit` falso. Use `f=geojson`, `outSR=4326`, `outFields=*`.
  - Filtre por bbox do polo com `geometry=<xmin,ymin,xmax,ymax>&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects`. Bbox AMACRO aproximado: `-66.0,-10.0,-60.0,-6.5`. Expanda se precisar.
- **Join** pelo número da autorização: PAMGIA `nu_autorizacao` = `NRO_AUTORIZACAO` em `poa.csv` / `pmfs.csv` / `asv.csv` / `uas.csv` / IF100.
  - Existem linhas duplicadas nos CSVs. Deduplique pela tupla `(autorização, espécie, produto, volume)` no POA.
- **POA** (`data/raw/poa.csv`): colunas `NRO_AUTORIZACAO, NRO_AUTORIZACAO_PMFS_VINCULADO, DATA_DE_VALIDADE, AREA_UPA, LATITUDE_UPA, LONGITUDE_UPA, PRODUTO, NOME_CIENTIFICO, NOME_POPULAR, VOLUME`. Use só os produtos que começam com "Tora".
  - Intensidade mediana esperada: cerca de 22,7 m³/ha (sanity check).
- **IF100** (`data/raw/if100/*.csv`, separador `;`): colunas `NRO_AUTORIZACAO, DATA_DE_EMISSAO, DATA_DE_VALIDADE, UF, MUNICIPIO, ATIVIDADE, PRODUTO, NRO_ARVORE_EXPLORADA, LATITUDE_ARVORE, LONGITUDE_ARVORE, NOME_CIENTIFICO, NOME_POPULAR, VOLUME_AUTORIZADO, VOLUME_EXPLORADO, DATA_DA_EXPLORACAO` (dd/mm/yy).
  - **ATENÇÃO**: as coordenadas vêm SEM sinal e com vírgula decimal, por exemplo `,437689;60,412819`.
    - Normalize: `lon = -abs(lon)`.
    - Latitude: no polo, todas são Sul, então `lat = -abs(lat)`. Ainda assim, valide contra o polígono. Se mais de 50% das árvores de uma autorização caírem a mais de 5 km do polígono com o sinal negativo, teste o sinal positivo e registre.
  - Escreva testes para essa normalização.
  - Os arquivos são grandes (até 120 MB). Leia com pandas em chunks e filtre pelas autorizações do polo.
- Hoje NÃO existem `dof_autorizacoes_csv/` descompactado com colunas conhecidas. Inspecione o cabeçalho; ele traz a AUTEX com volume por produto e espécie, inclusive para ASV.
- **DETER/PRODES (INPE TerraBrasilis WFS)**: `https://terrabrasilis.dpi.inpe.br/geoserver/ows`. Camadas `deter-amz:deter_amz` (campos de classe incluem `classname`, como DESMATAMENTO_CR, CS_DESORDENADO, CS_GEOMETRICO, DEGRADACAO, MINERACAO, e `view_date`) e `prodes-legal-amz:yearly_deforestation` (com campo de ano).
  - Use `outputFormat=application/json`, `srsName=EPSG:4326` e BBOX do polo. Pagine se necessário.
  - Baixe apenas a partir de 2021.
- Opcional, se der tempo: UC e TI (`prodes-legal-amz:conservation_units_legal_amazon`, `prodes-legal-amz:indigenous_area_legal_amazon`) e embargos IBAMA.

## Entregas (nesta ordem; a 1 e a 2 são urgentes, porque o AG-IMAGEM depende delas)
1. `pipeline/ingest/pamgia.py`: baixa os polígonos do polo e grava `data/processed/autorizacoes.parquet` (GeoParquet, EPSG:4326, com geometrias válidas via `make_valid`). Tipo normalizado: POA para PMFS/POA; ASV; UAS.
2. `pipeline/ingest/if100.py` → `data/processed/arvores_if100.parquet`: pontos normalizados de 2022+ só do polo, com coluna `dentro_upa` (tolerância de 20 m em UTM) e `dist_upa_m`.
3. `pipeline/ingest/poa.py` → `data/processed/poa_especies.parquet`: volume autorizado por autorização e espécie. Junte com DOF AUTEX para obter o volume autorizado de ASV/UAS, se a AUTEX existir.
4. `pipeline/ingest/inpe.py` → `data/processed/deter.parquet`, `prodes.parquet` (e `uc.parquet`, `ti.parquet` se der).
5. `pipeline/grid/celulas.py`: função `grade_celulas(aoi_geom_4326, tamanho_m=100) -> GeoDataFrame` alinhada em UTM, e `agrega_arvores(celulas, arvores) -> vol_declarado, n_arvores por célula`. Será usada pelo AG-ML e pelo AG-REGRAS.
6. `pipeline/ingest/regras_doc.py`: para cada autorização do polo, calcula:
   - C: árvores IF100 fora do polígono (mais de 20 m): quantidade e volume.
   - D: soma explorado vs autorizado (IF100 e POA); árvores com explorado > autorizado × 1,1; intensidade em m³/ha = volume explorado / `area_pamgia_ha`, com teto de 30.
   - E: datas de exploração fora de `[dt_valid_inicio, dt_valid_fim]`.
   - Grava em `data/processed/regras_doc.parquet`.
7. `pipeline/ingest/pretriagem.py` → `data/processed/pretriagem.csv`: ranking de candidatos para a análise de imagem.
   - Critérios POA: validade iniciada entre 2022 e 2025; com árvores IF100 (no mínimo 200); área de 100 a 5.000 ha; mais pontos para DETER no buffer de 2 km, para as flags C/D/E e para a exploração concentrada num período curto.
   - Saída: top 60 POA e top 20 ASV/UAS (ASV/UAS: 2022+, área de 20 a 2.000 ha, mais pontos para DETER/PRODES no buffer).
   - Colunas: `autex, tipo, uf, municipio, area_ha, validade_ini, validade_fim, n_arvores, data_expl_min, data_expl_max, n_deter_buffer, score_pre, motivo`.
8. Script único `pipeline/ingest/run_all.py` que roda 1→7 de forma idempotente, com cache: se o arquivo existe, pula, a menos que receba `--force`.

## Critério de pronto
`uv run python -m pipeline.ingest.run_all` gera todos os arquivos; `uv run pytest tests/ingest` passa. Imprima um resumo com contagens por tipo, quantidade de árvores e top 10 da pré-triagem.
Grave também `data/processed/README.md` com o esquema de cada arquivo (colunas e tipos), para os outros agentes.
