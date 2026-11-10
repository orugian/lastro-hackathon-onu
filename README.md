# Lastro

**O volume de madeira declarado tem lastro na floresta?**

Protótipo de triagem da exploração madeireira na Amazônia. Cruza autorizações e volumes públicos do IBAMA, árvores declaradas no IF100 e evidências Sentinel-2/CBERS para ordenar uma fila de fiscalização com indícios explicáveis.

> **Resultado experimental de triagem. Não constitui prova nem auto de infração.** O score é prioridade, não probabilidade de irregularidade. A conclusão exige vistoria e análise técnica humana.

## O protótipo

![Tela de triagem do Lastro com dados reais do polo AMACRO](<docs/img/triagem.png>)

*Triagem territorial com dados reais do polo AMACRO.*

![Tela de dossiê do Lastro](<docs/img/dossie.png>)

*Dossiê da autorização, com volumes, indícios e mapa.*

![Dossiê do Lastro com evidência de imagem](<docs/img/dossie-evidencia.png>)

*Evidência de imagem no dossiê. Capturas da demonstração original (06/11/2026).*

## Rodar o MVP

Pré-requisitos: **Python 3.11**, [uv](https://docs.astral.sh/uv/), **Node.js 24** e npm. Execute na raiz do repositório:

```powershell
.\scripts\serve.ps1
```

O script instala as dependências a partir dos lockfiles, gera os recursos estáticos e compila o frontend. Acesse **http://127.0.0.1:8000**. A primeira instalação precisa de internet. Não é necessário autenticar no Earth Engine, baixar dados brutos ou carregar o modelo ONNX para consultar a demo.

Em outros sistemas, ou para executar as etapas separadamente:

```sh
uv sync --locked
npm --prefix web ci
npm --prefix web run build
uv run --locked uvicorn api.main:app --host 127.0.0.1 --port 8000
```

A API usa os dados pré-processados incluídos em `data/artifacts/`. O acervo contém **1.142 autorizações reais e um cenário identificado como SIMULAÇÃO**, com 40 análises de imagem já processadas. Triagem, dossiês, mapas, impressão e métricas de confiabilidade usam esse acervo. As métricas descrevem a execução original; não são garantias de desempenho em outras regiões ou períodos.

### Dados simulados e frontend isolado

Para usar o acervo sintético na API, defina `LASTRO_ARTIFACTS=data/artifacts-mock` no ambiente antes de iniciá-la (PowerShell: `$env:LASTRO_ARTIFACTS = 'data/artifacts-mock'`).

```sh
npm --prefix web run dev
```

O Vite encaminha `/api` para a API local. Se ela não responder, o frontend usa dados **simulados**, gerados automaticamente por `predev`/`prebuild` em `web/public/mock/` a partir de `data/artifacts-mock/`. Essa cópia gerada não é versionada. O mock tem dois dossiês completos; os oito registros adicionais servem apenas para preencher a listagem. O frontend isolado não oferece análise ao vivo, impressão pela API nem fila de comunicações persistida.

## Análise ao vivo: preparação adicional

**Um clone novo é suficiente para consultar a demo, mas não para reprocessar novas imagens.** O botão de análise reutiliza o cache dos casos já completos. Para casos apenas documentais, o processamento exige bases intermediárias e modelos LightGBM, que não são distribuídos no repositório. Sem eles, a API informa indisponibilidade sem substituir o acervo por dados inventados.

Para preparar esse processamento:

1. Obtenha os dados nas [fontes públicas documentadas](docs/FONTES.md). Em `data/raw/`, disponha `poa.csv`, `asv.csv`, `uas.csv`, os CSVs IF100 de 2022 em diante em `if100/` e os CSVs DOF AUTEX em `dof_autorizacoes_csv/`.
2. Autentique a conta no Earth Engine (`uv run earthengine authenticate`) e defina **`LASTRO_EE_PROJECT`** com um projeto seu habilitado para Earth Engine. No PowerShell: `$env:LASTRO_EE_PROJECT = 'seu-projeto-gee'`. Credenciais devem permanecer fora do Git.
3. Para usar a confirmação U-Net, instale [Git LFS](https://git-lfs.com/) e execute `git lfs install` e `git lfs pull`. O peso `models/lastro_unet.onnx` tem aproximadamente 96 MiB; um ponteiro LFS sem o objeto não é um modelo utilizável. O treinamento original da U-Net não faz parte deste MVP.
4. Execute as etapas de preparação abaixo, na raiz. Elas consultam serviços externos, podem demorar e atualizam os artefatos locais. Não são necessárias para apresentar a demo:

```sh
uv run python -m pipeline.ingest.run_all
uv run python -m pipeline.detect.train
uv run python -m pipeline.volume.calibrar --baixar --n 72
uv run python -m pipeline.volume.calibrar
uv run python -m pipeline.export.run --top 80
```

A ingestão produz as tabelas de autorizações, árvores, espécies, regras, DETER/PRODES e a pré-triagem em `data/processed/`. O treino gera `data/processed/ml/lgbm_detector.txt` e `threshold.json`; a calibração gera os modelos de volume. Bases públicas podem mudar: uma nova execução não necessariamente reproduz os números do acervo original. Sem os modelos quantílicos, o estimador usa uma aproximação linear, que não equivale à calibração publicada.

`LASTRO_DETECTOR=lightgbm` seleciona apenas LightGBM; por padrão, a detecção espacial usa LightGBM confirmado pela U-Net quando o ONNX está disponível. O volume sempre usa LightGBM. Use a raiz padrão `data/artifacts/` para reprocessamento: `LASTRO_ARTIFACTS` altera a leitura da API, não o destino do pipeline.

## Comunicações e limites de segurança

Casos com prioridade ≥ 70 e ao menos um indício geram um protocolo local. **O conector padrão é `simulado`: não há envio externo.** A confirmação exige identificação e justificativa, mas isso **não é autenticação de usuário**. Cenários SIMULAÇÃO nunca são enviados.

A aplicação é uma **demo local**, sem autenticação ou controles de produção. Mantenha a API em `127.0.0.1`; não a exponha diretamente à internet. Os conectores SMTP e Fala.BR só devem ser configurados após revisão de segurança e acordo institucional. Não há submissão automática por API pública do Fala.BR.

Configurações opcionais por variáveis de ambiente:

| Variável | Padrão / finalidade |
|---|---|
| `LASTRO_ARTIFACTS` | `data/artifacts/`, com fallback para `data/artifacts-mock/` |
| `LASTRO_EE_PROJECT` | Sem padrão; projeto do operador para reprocessar imagens |
| `LASTRO_DETECTOR` | `unet`; aceita `lightgbm` |
| `LASTRO_CONECTOR` | `simulado`; mantenha assim para demonstração |
| `LASTRO_CONFIRMACAO_HUMANA` | `1`; mantenha habilitada |
| `LASTRO_LIMIAR_COMUNICACAO` | `0.70` |
| `LASTRO_COMUNICACOES` | `data/comunicacoes/`, saída local não versionada |

O aplicativo não carrega `.env` automaticamente; exporte as variáveis no terminal/processo. Nunca versione credenciais, arquivos `.env`, dados brutos ou a fila local de comunicações.

## Código e documentação

```text
api/                  API FastAPI e dossiê imprimível
web/                  React + TypeScript + Vite + MapLibre
contracts/            Contratos Pydantic e TypeScript dos artefatos
pipeline/             Ingestão, processamento, detecção, volume, regras e comunicação
models/               Peso ONNX para confirmação espacial (Git LFS)
data/artifacts/       Acervo pré-processado consumido pela demo
data/artifacts-mock/  Acervo sintético de fallback
scripts/              Inicialização e geração do acervo sintético
docs/                 Fontes, método e limitações dos modelos
```

- [Método](docs/METODO.md): regras, limiares e conversão imagem → volume.
- [Model card](docs/MODEL_CARD.md): protocolos, métricas históricas, vieses e usos não pretendidos.
- [Fontes e licenças](docs/FONTES.md): proveniência, datas e atribuições das bases.

O acervo não exporta nomes, CPF ou CNPJ de detentores. Números de autorização e geometrias públicas são mantidos para rastreabilidade. As licenças das fontes continuam aplicáveis; em particular, dados INPE e Copernicus exigem as atribuições indicadas na documentação.
