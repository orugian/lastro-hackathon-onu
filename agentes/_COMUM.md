# Contexto comum: projeto LASTRO (hackathon, 8 h)

Você é um agente de desenvolvimento autônomo. Não faça perguntas e não peça confirmação. Decida, implemente, teste e entregue.

## Produto
**Lastro**: triagem antifraude de exploração madeireira na Amazônia. Responde à pergunta: o volume de madeira declarado/autorizado tem lastro físico na floresta?
O sistema cruza quatro fontes:
- autorizações Sinaflor (polígonos PAMGIA);
- árvores declaradas como exploradas (IBAMA IF100, com coordenada, volume e data);
- DOF;
- imagens de satélite (Sentinel-2 via Google Earth Engine e CBERS-4A WPM 2 m via INPE/BDC).

Os resultados são **indícios para priorizar fiscalização**, nunca prova. Nunca escreva "fraude", "ilegal" ou "criminoso" como afirmação. Use "indício", "divergência", "prioridade de fiscalização".

Polo da demo: **AMACRO**, que compreende o Sul do Amazonas (Humaitá, Lábrea, Novo Aripuanã, Manicoré, Canutama) e Porto Velho/Candeias do Jamari (RO).
Regimes:
- **POA/PMFS**: manejo seletivo. É o caso principal.
- **ASV/UAS**: corte raso. É o caso secundário.

## Ambiente
- Windows; o shell é PowerShell 5 (não existe `pwsh`). Diretório raiz: `C:\Users\orugi\Documents\Projetos\Hackathon\SOLUCAO-FINAL`.
- Python 3.11 gerenciado com **uv**. Rode tudo com `uv run python ...` e `uv run pytest ...`.
  - Pacotes já instalados: geopandas, shapely, pyproj, rasterio, numpy, pandas, pyarrow, scikit-image, scikit-learn, lightgbm, earthengine-api, pystac-client, planetary-computer, fastapi, uvicorn, pydantic, requests, pytest, httpx, matplotlib, pillow.
  - Para adicionar um pacote: `uv add <pkg>`. Evite fazer isso sem necessidade, porque outros agentes rodam em paralelo.
- Google Earth Engine já está autenticado: `import ee; ee.Initialize(project='project-f5ab0bff-aa9b-4cb2-97d')`.
- Node 24 e npm. O front fica em `web/` (Vite + React + TS + maplibre-gl).
- Há rede.

## Regras de colaboração (outros agentes trabalham em paralelo)
- **Escreva SOMENTE nas pastas que a sua spec diz que são suas.** Outras pastas são só leitura.
- **Contrato de dados** (fonte única da verdade): `contracts/models.py` (pydantic) e `contracts/types.ts`. Não altere esses arquivos. Se faltar algo no contrato, use campos opcionais extras dentro de dicts livres e registre o pedido no seu relatório final.
- Há um mock completo e válido em `data/artifacts-mock/`, gerado por `scripts/make_mock.py`. Use-o como exemplo do formato.
- Dados brutos já baixados ficam em `data/raw/` e são só leitura:
  - `poa.csv` (POA Amazônia Legal, separador `;`, UTF-8);
  - `pmfs.csv`, `asv.csv`, `uas.csv`;
  - `if100/volumes_explorados_if_100_ano_20XX.csv` (2017–2026);
  - `pamgia_amz_attrs.json` (atributos, sem geometria, dos 16.893 polígonos no bioma Amazônia);
  - `dof_autorizacoes_csv/` (AUTEX);
  - `dof_transportes_csv.zip` (4,4 GB, NÃO descompacte inteiro).
- Dados intermediários vão para `data/processed/` e artefatos finais para `data/artifacts/`. Respeite o layout do contrato.
- Não rode `git commit`; o orquestrador faz os commits.
- Escreva testes pytest para a lógica crítica em `tests/<sua_area>/`.
- Seja pragmático: entregue algo funcionando cedo e depois melhore. Prazo curto.
- Datas em ISO. Áreas em ha e volumes em m³. Calcule áreas e distâncias em UTM (EPSG:31980 para longitude entre -66 e -60; EPSG:31981 para longitude entre -60 e -54), nunca em graus.

## Relatório final (sua última mensagem)
Markdown curto com:
1. o que foi entregue (arquivos);
2. como rodar;
3. o que foi verificado (comandos e saídas-chave);
4. pendências e riscos;
5. pedidos ao orquestrador.
