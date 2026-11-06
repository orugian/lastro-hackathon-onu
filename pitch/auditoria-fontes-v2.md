# Lastro — auditoria de fontes para diretores (pitch de 7 minutos)

## Parecer executivo

**Há demonstração técnica com dados públicos reais, não evidência de impacto financeiro ou de ilegalidade comprovada.** A tese defensável é priorizar revisão humana com evidências rastreáveis. O principal risco da apresentação é misturar versões: roteiro, cabeçalho do índice, casos e dossiês não estão sincronizados.

Auditoria local, sem web, sem alterar código ou dados do produto, sem reexecutar treino/ingestão. Skills lidas: `ml-best-practices` e `canvas` (dispensado por existir entregável específico em Markdown/JSON). Valores são dos artefatos disponíveis, não certificação externa. Base calculável: [métricas auditadas](<pitch/metricas-v2.json>).

## 1. Métricas liberadas, com denominador e contexto

| Métrica verificável | Denominador / leitura permitida | Evidência |
|---|---|---|
| **1.142 autorizações reais**, sendo 1.079 POA, 40 ASV e 23 UAS | Acervo do polo: sete municípios AM/RO; não Amazônia inteira. Array tem uma entrada simulada adicional, excluída. | [Índice:5–26](<data/artifacts/index.json#L5-L26>), [recorte territorial](<docs/METODO.md#L50-L68>), [recontagem](<pitch/metricas-v2.json>) |
| **329.288 registros IF100 em 293 autorizações**; **1,87 milhão m³ declarados** | Tora, arquivos/data de exploração 2022+, duplicatas exatas removidas. Registros não necessariamente árvores físicas únicas. 293/1.142 têm registros IF100. Soma dos valores dos casos: 1.870.553,05 m³ (já arredondados). Não dizer “1,87 milhão m³ ilegais” ou integralmente verificados por satélite. | [Método:52–57](<docs/METODO.md#L52-L57>), [semântica de registros](<data/processed/README.md#L5-L9>), [índice:23–24](<data/artifacts/index.json#L23-L24>), [recontagem](<pitch/metricas-v2.json>) |
| **39 autorizações reais com análise de imagem (3,42%)** | 39/1.142; 31 POA + 4 ASV + 4 UAS. Processamento de imagem não implica 100% de observabilidade. Seleção é dirigida por pré-triagem, não amostra aleatória. | Recontagem de `casos` filtrando `source_mode === real` e `analise_imagem === true`: [resultado](<pitch/metricas-v2.json>); [critérios de seleção](<docs/METODO.md#L64-L68>) |
| **62 autorizações reais com ≥1 indício (5,43%)** | 62/1.142 no acervo atual; não prevalência de ilegalidade, taxa de acerto ou autuações. Flags se sobrepõem. A=1, B=35, C=11, D=10, E=29, F2=2, F6=0. | Recontagem de `casos` reais com `flags.some(status === indicio)`: [resultado](<pitch/metricas-v2.json>); [significado de triagem](<docs/MODEL_CARD.md#L140-L152>) |
| **A: 1 indício, 1 inconclusivo, 29 sem indício** | Somente 31 POA reais com imagem. Não usar o total de 1.142 como denominador da avaliação visual de A. Não usar A como caso principal sem revisão adicional. | [recontagem](<pitch/metricas-v2.json>); caso real com A: [índice:343 em diante](<data/artifacts/index.json#L343>) |
| **Detector LightGBM: IoU 0,561; F1 0,719; recall 0,694**, vs Otsu IoU 0,283 | 65.500 pixels, 36 blocos de 5 km, cinco folds espaciais, 2022–2024; amostra favorece alertas. Positivos=29.500 e negativos=36.000 na matriz; não prevalência regional. | [métrica e protocolo](<data/artifacts/metrics/detector.json#L2-L41>), [limites](<docs/MODEL_CARD.md#L80-L85>) |
| **Recall seletivo/degradação 56,5%** | 10.170 verdadeiros positivos / 18.000 pixels positivos DETER; estrato de 54.000 pixels inclui os mesmos 36.000 negativos. É o limite relevante para o problema de manejo seletivo. | [detector:41](<data/artifacts/metrics/detector.json#L41>), [model card:46–55](<docs/MODEL_CARD.md#L46-L55>) |
| **U-Net local: IoU 0,729 vs LightGBM 0,452**, no mesmo teste | 3.106.574 pixels rotulados, 21 blocos locais; 11 blocos vistos excluídos. U-Net vence em 19/21 blocos. Não comparar diretamente 0,729 com 0,561 do protocolo anterior. Subamostra balanceada do mesmo estudo: 37.500 pixels, IoU 0,660 vs 0,554. | [avaliação local:2–40](<data/processed/dl/avaliacao_local.json#L2-L40>), [subamostra:60–94](<data/processed/dl/avaliacao_local.json#L60-L94>), [data de geração:284](<data/processed/dl/avaliacao_local.json#L284>) |
| **Intervalo de volume: cobertura 84,2% por célula e 88,9% por UPA**, nominal 80% | 17.193 células válidas / 72 UPAs, validação agrupada por UPA. Cobertura é do volume **declarado**, não aferição física em campo nem acurácia da fiscalização. | [calibração:2–8](<data/artifacts/metrics/calibracao.json#L2-L8>), [CV:8–33](<data/processed/volume/metricas_cv.json#L8-L33>) |
| **Limite da estimativa: R² célula 0,070; MAE 11,1 m³/ha; largura média 32,4 m³/ha** | Não prometer cubagem precisa por árvore/célula. UPA Monte Carlo após conformal: R² 0,056, erro relativo mediano 29,5%. Não selecionar o R² 0,55 de outro agregador como se fosse resultado do Monte Carlo final. | [CV:8–33](<data/processed/volume/metricas_cv.json#L8-L33>) |
| **Blocos de 9 ha: cobertura 66,5%; A dispara em 5/72 UPAs de calibração (6,94%)** | 2.554 blocos; cobertura abaixo dos 80% nominais. As UPAs não têm verdade de campo comprovadamente regular: 6,94% não é taxa de falso positivo certificada. | [CV:41–76](<data/processed/volume/metricas_cv.json#L41-L76>), [contaminação possível](<docs/MODEL_CARD.md#L125-L136>) |
| **56.257 polígonos DETER e 40.122 PRODES** | Consulta desde 2021 no bbox [-67,5; -11; -59; -5], não quantidade de infrações vinculadas às 1.142 autorizações. | [proveniência DETER:4–12](<data/processed/deter.proveniencia.json#L4-L12>), [PRODES:4–12](<data/processed/prodes.proveniencia.json#L4-L12>) |

### Reprodutibilidade da contagem

O [índice auditado](<data/artifacts/index.json>) declara geração `2026-11-06T08:15:23+00:00`; SHA-256 `915c0a356a2ddc4fcc73f91abab8ac1cfb766c1c98c4e168422872963c8bacfd`. Recontagem executada com Node, leitura JSON e filtro explícito por origem, sem modificar a fonte:

```js
const reais = indice.casos.filter(c => c.source_mode === 'real');
const imagens = reais.filter(c => c.analise_imagem === true);
const indicios = reais.filter(c => c.flags.some(f => f.status === 'indicio'));
const porFlag = codigo => reais.filter(c => c.flags.some(f =>
  f.codigo === codigo && f.status === 'indicio')).length;
```

O [cabeçalho:5–26](<data/artifacts/index.json#L5-L26>) informa **38/61/B34**, mas seu array real retorna **39/62/B35**. O [roteiro:41–56](<pitch/ROTEIRO.md#L41-L56>) é ainda mais antigo (48 indícios). Preferir o array auditado; não afirmar que todo o produto está sincronizado.

## 2. Caso real recomendado — POA de Candeias do Jamari

Mostrar AUTEX mascarado em slides. Fonte de detalhe: [dossiê:1–79](<data/artifacts/cases/20112202459084/dossier.json#L1-L79>), processado às **14:09:32Z**. O [resumo do índice:29–107](<data/artifacts/index.json#L29-L107>) é das **08:04:15Z**.

- Base estável: **494 registros**, **123,25 ha**, **2.445,89 m³ declarados**, **3.372,69 m³ autorizados**; validade **04/12/2024–04/12/2025**. A/D sem indício; B/C/E com indício.
- **C: 45/494 registros (9,1%)**, correspondendo a **238,9 m³**, com coordenadas de 20 m a 5 km fora da UPA. É divergência cadastral/geográfica, não prova de extração ilegal: [evidência:179–196](<data/artifacts/cases/20112202459084/dossier.json#L179-L196>).
- **E: 490/494 registros (99,2%) com data fora da validade**; declarações de 25/06/2025 a 26/10/2026. A divergência decorre das datas IF100; a imagem, isoladamente, é inconclusiva sobre a validade: [evidência:250–283](<data/artifacts/cases/20112202459084/dossier.json#L250-L283>).
- **B opcional:** **8,41 ha** em quatro polígonos fora da UPA e **9,21 ha** dentro em células sem declaração. Não atribuir autoria. Os **103,64 ha** de contexto regional estão explicitamente **excluídos**: [evidência:132–177](<data/artifacts/cases/20112202459084/dossier.json#L132-L177>).
- **Não misturar versões:** índice tem 38,73 ha de distúrbio dentro / 14,15 fora; dossiê atual tem 19,59 dentro / 8,41 fora. Nos 39 dossiês reais com imagem examinados, **11 diferem nas áreas do índice**, mas **nenhum difere nos códigos/status das flags**. As contagens de indícios permanecem compatíveis; áreas não.
- **Limite temporal concreto:** pós vai até 05/10/2026, mas última exploração declarada é 26/10/2026. Não dizer que a imagem pós cobre toda a exploração. Há 6/175 células não observáveis e CBERS não processado: [limitações:652–661](<data/artifacts/cases/20112202459084/dossier.json#L652-L661>), [cronologia:689–697](<data/artifacts/cases/20112202459084/dossier.json#L689-L697>).

**Fala segura:** “Em um caso real, o Lastro reúne 45 registros declarados fora do polígono e 490 datas fora da validade, com mapa, regra e fonte. Isso permite ao analista decidir o que verificar; não substitui sua conclusão.”

## 3. Métricas proibidas como resultado real

1. **Cenário `SIM-...` e todos os mocks.** A entrada simulada tem 5.760 registros e 28.754,59 m³, flags A/B/C: [índice:190–267](<data/artifacts/index.json#L190-L267>). Foram injetados 1.600 registros fictícios, 7.928,9 m³ e três árvores fora da UPA: [injeção:592–598](<data/artifacts/cases/SIM-20132202313817/dossier.json#L592-L598>), [aviso:652](<data/artifacts/cases/SIM-20132202313817/dossier.json#L652>). Nunca somar ao alcance real. [Detector mock:25–41](<data/artifacts-mock/metrics/detector.json#L25-L41>) tem IoU 0,61/F1 0,76 com `MOCK`: proibidos como validação.
2. **“2 casos reais de volume sem lastro”.** O [deck:275](<pitch/deck.html#L275>) conta A sobre reais+simulado. O [gerador:258–264](<pitch/build_deck.py#L258-L264>) confirma a mistura. Real=1, simulado=1.
3. **“11.084,1 m³ de fraude/prejuízo recuperado”.** Campo p50 do [cabeçalho:25](<data/artifacts/index.json#L25>) não é dano comprovado. Não monetizar nem interpretar agregado de células como confirmação da regra A, que exige blocos/UPA.
4. **Score/confiança como probabilidade de ilegalidade.** São ordenação/regra; [método:199–206](<docs/METODO.md#L199-L206>). “Sem indício”, ausência de flag e “não avaliado” não certificam conformidade.
5. **Métricas de pesquisa como desempenho de produção ou dados de campo.** Não cruzar protocolos 65.500 px / Colab 1.977.980 px / local 3.106.574 px. Não chamar recall de pixel de taxa de detecção de fraudadores.
6. **32% do Pará como dado AMACRO.** Trata-se de referência externa de outro território, apenas documentada localmente e não checada nesta auditoria: [fontes:24–28](<docs/FONTES.md#L24-L28>). Preferir omitir no pitch de sete minutos.
7. **Receita, ROI, economia em R$, custo operacional, horas economizadas, multas/volumes recuperados, desmatamento evitado.** Não encontramos comprovação no recorte auditado. Nem “dados gratuitos” prova operação sem custo.

## 4. Limitações que devem aparecer

- **Snapshot inconsistente:** cabeçalho, array, dossiês e textos representam diferentes estágios. Congelar os números desta auditoria na apresentação, sem “corrigir” o produto nesta tarefa.
- **Modelo efetivamente mostrado:** o [dossiê:544–546](<data/artifacts/cases/20112202459084/dossier.json#L544-L546>) já usa U-Net para detecção e LightGBM para volume. O [model card:74](<docs/MODEL_CARD.md#L74>) e métricas antigas ainda dizem “pesos não exportados”. Não afirmar integração homogênea em todos os casos; há evolução parcial documentada.
- **Sem validação de campo/temporal independente demonstrada:** rótulos INPE são fracos; clareiras pequenas não são captadas; amostra favorece alertas; blocos vizinhos sem buffer podem inflar métricas: [limites do detector](<docs/MODEL_CARD.md#L80-L85>).
- **Volume aprende declaração, não madeira medida:** cobertura ampla não elimina R² baixo nem contaminação possível: [calibração](<docs/MODEL_CARD.md#L125-L136>). O protocolo afirma monotonicidade, mas a [observação da calibração:137](<data/artifacts/metrics/calibracao.json#L137>) declara não haver restrição monotônica com o objetivo quantílico; não vender essa propriedade.
- **Lacunas de integração:** DOF Transportes, GEDI/Canopy e UC/TI/embargos não estão integrados conforme [fontes:14–20](<docs/FONTES.md#L14-L20>) e [F6 no caso real:660](<data/artifacts/cases/20112202459084/dossier.json#L660>). F6=0 não significa inexistência de sobreposição.
- **Dados pessoais:** não dizer “não existem no projeto”: o schema processado contém nome/CPF/CNPJ em [metadados:53–57](<data/processed/README.md#L53-L57>). A promessa documentada é não exportá-los/exibi-los; manter identificação mascarada na apresentação.
- **Norma e jurisdição:** teto de 30 m³/ha exige confirmação especializada; expansão fora do polo exige revalidação: [método:183](<docs/METODO.md#L183>), [usos:147–152](<docs/MODEL_CARD.md#L147-L152>).

## 5. Narrativa institucional recomendada — 7 minutos

1. **0:00–0:45 | Decisão de negócio:** como escolher quais autorizações merecem análise técnica primeiro, sem transformar suspeita em acusação?
2. **0:45–1:35 | Proposta:** reunir autorizado, declarado e observado em fila priorizada e dossiê rastreável. Benefício pretendido: foco e consistência da análise; ainda não medido em produtividade.
3. **1:35–2:25 | Escala comprovada:** 1.142 autorizações, 329.288 registros e 1,87 milhão m³ declarados; explicar imediatamente que 39 têm imagem e 62 têm algum indício, não 62 infrações.
4. **2:25–4:10 | Caso real:** Candeias, mapa + C/E + regra/fonte; B opcional. Sem titular e sem “árvore fantasma”. Mostrar também que A/D permanecem sem indício.
5. **4:10–5:10 | Evidência técnica:** comparação no mesmo teste local (U-Net IoU 0,729 vs 0,452), com denominador; volume por intervalo e revisão humana. Métrica de pixel não vira precisão jurídica.
6. **5:10–6:10 | Viabilidade e fronteira:** protótipo com dados públicos, caches, evidências e aplicação existente; lacunas de integração, atualização e validação de campo explícitas. Sem prometer SLA, escala nacional ou custo zero.
7. **6:10–7:00 | Pedido aos diretores:** aprovar um piloto institucional delimitado, com órgão parceiro, amostra validada por especialistas e metas a medir. Medir tempo por análise, concordância dos revisores, rendimento da fila, custo computacional/campo e atualização. Esses são objetivos futuros, não resultados já atingidos.

**Frase final:** “O Lastro não decide quem está irregular. Entrega ao analista uma fila explicável e as evidências para decidir onde investigar primeiro.”

**Financeiro:** nesta versão, apresentar somente “impacto financeiro ainda não aferido; piloto necessário para medir custo-benefício”. Não atribuir valores monetários aos metros cúbicos.
