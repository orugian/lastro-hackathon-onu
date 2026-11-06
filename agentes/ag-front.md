# AG-FRONT: interface React + Vite + MapLibre

**Suas pastas:** `web/` (já tem scaffold Vite react-ts e `maplibre-gl` instalado), `tests/web/`.

## Objetivo
Interface de nível profissional para a banca de um hackathon, em português do Brasil. É o que a banca vê, então a qualidade visual importa muito. Consome a API (`/api/...`, ver abaixo) e usa os tipos de `contracts/types.ts`: copie esse arquivo para `web/src/types.ts` e não altere os campos.

## Identidade visual (herdada do RAIZTRACE)
- **Cores**:
  - floresta `#173a2c` (cabeçalho, tinta), floresta escura `#0e261d` (nav);
  - papel `#f3f4e8` (fundo de leitura), branco nos painéis;
  - lima `#c5f67c` (seleção e foco);
  - âmbar `#78350f` sobre `#fffbeb` (incerteza e aviso de simulação);
  - DETER `#d97706`;
  - erro e indício alto `#991b1b`.
- **Tipografia**: Georgia nos títulos de seção, sans do sistema no corpo (14–15 px), `tabular-nums` nos números e mono só em identificadores (nº AUTEX).
- **Proibições**: sem gradiente em texto, sem emojis como ícones (use SVG inline com traço uniforme), sem cards aninhados, sem sombras duras. Nenhuma informação depende só de cor: sempre há rótulo de texto.
- **Estados obrigatórios**: carregando, erro recuperável, vazio e não avaliado.
- **Selo fixo** no cabeçalho e no dossiê: "Resultado experimental de triagem · não constitui prova nem auto de infração". Se `source_mode == "simulado"`, mostre também um selo âmbar "SIMULAÇÃO".

## Telas (rotas simples com hash ou estado; sem router pesado)
1. **Triagem** (`#/`):
   - Mapa MapLibre ocupando cerca de 2/3 da tela, com os casos como círculos coloridos por score. Use o `centroide` do index.
   - Lista lateral ranqueada com nº AUTEX (mono), tipo, município/UF, score como barra com número, chips das flags com status "indicio", volume autorizado vs declarado vs estimado p50, e o ícone "imagem analisada" (`analise_imagem`).
   - Filtros: UF, tipo, flag, só com imagem.
   - Totais do `index.totais` no topo, em texto discreto, sem métricas-herói.
   - Clicar abre o Dossiê.
2. **Dossiê** (`#/caso/{autex}`). É a tela mais importante.
   - **Mapa principal com comparador antes/depois.** Implemente um slider "swipe" com dois mapas MapLibre sincronizados e clip CSS (sem lib externa):
     - lado esquerdo = imagem `par: "pre"`;
     - lado direito = imagem `par: "pos"`;
     - seletor de sensor (Sentinel-2 / CBERS-4A 2 m) quando houver os dois.
     - As imagens são `image` sources do MapLibre com `coordinates` vindas de `bounds` [minx, miny, maxx, maxy] → [[minx,maxy],[maxx,maxy],[maxx,miny],[minx,miny]].
   - **Camadas vetoriais** (toggle na legenda):
     - `upa` (contorno lima tracejado);
     - `buffer` (contorno fino);
     - `celulas` coloridas por `classe`: sem_lastro = magenta/roxo forte, nao_declarado = vermelho, consistente = verde suave, sem_atividade = transparente, nao_observavel = cinza hachurado;
     - `arvores` (pontos pequenos; destaque em vermelho os com `dentro_upa=false`; agrupe se houver mais de 5 mil);
     - `mudanca` (contorno vermelho);
     - `deter` (laranja);
     - `prodes`;
     - camada `dndvi` (PNG RGBA) opcional.
   - Popups nas células com volume declarado vs p10/p50/p90 e nas árvores com espécie, volume e data.
   - **Painel lateral**:
     - cabeçalho com AUTEX, tipo, município/UF, validade e situação;
     - **gráfico de barras de volume**: autorizado | declarado explorado | estimado pela imagem, com barra de erro p10–p90. Use SVG próprio, sem lib;
     - lista de **flags** (`flags_detalhe`) com status, severidade, confiança (%) e regra; ao expandir, as evidências. **Clicar numa evidência com `camada`/`filtro` destaca essa camada ou feição no mapa e dá zoom**;
     - linha do tempo (`linha_do_tempo`);
     - espécies (tabela compacta);
     - parâmetros de volume;
     - limitações;
     - proveniência (fonte, data e link).
   - Botão "Dossiê imprimível" abre `/api/cases/{autex}/dossier.html`.
3. **Confiabilidade** (`#/confiabilidade`):
   - **Detector**: protocolo em texto, tabela comparando os modelos (IoU, F1, precisão, recall), matriz de confusão do modelo selecionado e o texto de `obs`.
   - **Calibração de volume**: gráfico SVG da `curva` (fração de distúrbio → p10/p50/p90 em m³/ha, como banda), R², MAE, **cobertura empírica p10–p90 vs nominal 80%** com explicação em linguagem simples e `n_upas`/`n_celulas`.
   - Seção "Como ler estes números" e "Limites conhecidos".
4. Cabeçalho global com o nome **Lastro**, o subtítulo "O volume declarado tem lastro na floresta?", a navegação entre as 3 telas e um botão **"Analisar autorização"**:
   - abre um modal com input de nº AUTEX;
   - chama `POST /api/analyze/{autex}` e faz polling de `GET /api/jobs/{id}` com barra de progresso e etapa;
   - ao terminar, navega para o dossiê;
   - em caso de erro, mostra a mensagem amigável.

## API (servida pelo AG-API em paralelo; use o mock enquanto isso)
`GET /api/health`, `/api/index`, `/api/cases/{autex}`, `/api/cases/{autex}/layers/{nome}` (GeoJSON), `/api/cases/{autex}/img/{arquivo}` (PNG, onde arquivo é o basename de `imagem.png`), `/api/metrics/detector|calibracao`, `POST /api/analyze/{autex}`, `GET /api/jobs/{id}`.

Durante o desenvolvimento, configure o proxy do Vite `/api` → `http://127.0.0.1:8000`. Como a API pode ainda não estar no ar, implemente também um **modo de dados estáticos**: se `/api/health` falhar, leia direto de arquivos estáticos copiados de `data/artifacts-mock` para `web/public/mock/` (mesmo layout). Faça a cópia com um script npm `sync-mock`.

## Basemap
O mapa precisa funcionar **offline**. Use fundo sólido papel/escuro e as imagens de satélite do próprio caso. Basemap raster OSM ou Esri World Imagery como camada opcional desligável, com atribuição. Inclua contornos simples de UF se quiser, com um GeoJSON pequeno embutido.

## Qualidade
- TypeScript sem `any` desnecessário; componentes pequenos.
- Sem dependências pesadas novas. Permitidas: nenhuma além do maplibre-gl, salvo se for realmente necessário e leve.
- Layout desktop 1440×900 primeiro (é o projetor da banca), responsivo aceitável em 1280×720.
- `npm --prefix web run build` sem erros de TS.
- Rode o dev server, abra com Playwright (`npx playwright` já pode estar disponível; senão use `npx -y playwright@latest install chromium`) e tire screenshots das 3 telas em `tests/web/screens/`. Olhe as screenshots e corrija problemas visuais. Repita pelo menos 2 vezes.

## Critério de pronto
`npm --prefix web run build` passa. As 3 telas funcionam com o mock (via API ou via estático). Há screenshots em `tests/web/screens/`.
